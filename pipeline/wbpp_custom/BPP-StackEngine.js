// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-StackEngine.js - Released 2026-05-10T11:05:00Z
// ----------------------------------------------------------------------------
//
// This file is part of:
// - WeightedBatchPreprocessing script version 3.0.1
// - FastBatchPreprocessing script version 1.2.1
//
// Copyright (c) 2019-2026 Roberto Sartori
// Copyright (c) 2020-2021 Adam Block
// Copyright (c) 2019 Tommaso Rubechi
// Copyright (c) 2012 Kai Wiechen
// Copyright (c) 2012-2026 Pleiades Astrophoto
//
// The use of this source code is governed by the PixInsight Class Library
// License Version 2.0, which can be found in the LICENSE file included with
// this distribution, as well as at:
// https://pixinsight.com/license/PCL-License-2.0.html
// ----------------------------------------------------------------------------

/**
 * Main StackEngine object constructor
 *
 */
var StackEngine = class
{
   constructor()
   {
      this.diagnosticMessages = new Array;

      // memoization cache
      this.findGroupMemoization = {};

      // allocate structures
      this.overscan = new Overscan;
      this.combination = new Array( 4 );
      this.rejection = new Array( 4 );
      this.percentileLow = new Array( 4 );
      this.percentileHigh = new Array( 4 );
      this.sigmaLow = new Array( 4 );
      this.sigmaHigh = new Array( 4 );
      this.linearFitLow = new Array( 4 );
      this.linearFitHigh = new Array( 4 );
      this.ESD_Outliers = new Array( 4 );
      this.ESD_Significance = new Array( 4 );
      this.RCR_Limit = new Array( 4 );

      this.groupsManager = new FrameGroupsManager();

      this.operationQueue = new BPPOperationQueue();

      // generic execution cache object handled by pipeline steps
      this.executionCache = new ExecutionCache();

      // console logger
      this.consoleLogger = new ConsoleLogger();

      // process logger
      this.processLogger = new ProcessLogger();

      // domain classes
      this.parametersManager = new ParametersManager( this );
      this.calibrationMatcher = new CalibrationMatcher( this );
      this.subframeAnalyzer = new SubframeAnalyzer( this );
      this.imageProcessor = new ImageProcessor( this );
      this.plateSolver = new PlateSolver( this );
      this.pipelineManager = new PipelineManager( this );
      this.diagnosticsManager = new DiagnosticsManager( this );
   }

   // ----------------------------------------------------------------------------
   // REFERENCE FRAME MANAGEMENT
   // ----------------------------------------------------------------------------
   /**
    * Returns an array of reference frame modes available.
    *
    * This function computes and returns the list of best reference frame modes available.
    *
    * @returns {Array<String>} An array containing the reference frame modes.
    */
   getBestReferenceFrameModes()
   {
      // store the current selected item
      let selections = [ "manual", "auto" ];
      let postProcessKeywords = engine.keywords.keywordsForMode( BPP.GroupingMode.POST );
      for ( let i = 0; i < postProcessKeywords.length; ++i )
         selections.push( "auto by " + postProcessKeywords[ i ].name );
      // cached reference frames are available only in WBPP
      return selections;
   }

   /**
    * Sets the best reference frame mode based on the provided index.
    *
    * @param {Number} index The index of the selected reference frame mode.
    */
   setBestReferenceFrameMode( index )
   {
      let entries = this.getBestReferenceFrameModes();
      let string = entries[ index ];
      if ( string == "manual" )
      {
         this.bestFrameReferenceMethod = BPP.BestReferenceMethod.MANUAL;
         this.bestFrameReferenceKeyword = "";
      }
      else if ( string == "auto" )
      {
         this.bestFrameReferenceMethod = BPP.BestReferenceMethod.AUTO_SINGLE;
         this.bestFrameReferenceKeyword = "";
      }
      else
      {
         this.bestFrameReferenceMethod = BPP.BestReferenceMethod.AUTO_KEYWORD;
         this.bestFrameReferenceKeyword = string.replace( "auto by ", "" );
      }
   }

   /**
    * Returns the index of the current best reference frame mode.
    *
    * @returns {Number} The index corresponding to the current best reference frame mode.
    */
   bestReferenceFrameModeIndex()
   {
      if ( this.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL || this.bestFrameReferenceMethod == BPP.BestReferenceMethod.AUTO_SINGLE )
         return this.bestFrameReferenceMethod;

      let options = this.getBestReferenceFrameModes().map( item => item.replace( "auto by ", "" ) );

      for ( let i = 0; i < options.length; ++i )
         if ( options[ i ] == this.bestFrameReferenceKeyword )
            return i;

      // error, not able to find the index. Change the method to AUTO SINGLE
      this.bestFrameReferenceMethod = BPP.BestReferenceMethod.AUTO_SINGLE;
      return 1;
   }

   // ----------------------------------------------------------------------------
   // GROUPS GETTERS
   // ----------------------------------------------------------------------------

   //
   /**
    * Returns a sorted list of groups of a given type and mode.
    *
    * @param {ImageType} type type of groups to be retrieved
    * @param {WBPPGroupingMode} mode the grouping mode
    * @returns the sorted list of groups
    */
   getSortedGroupsOfType( type, mode )
   {
      let groupsByType = [];
      let groups = this.groupsManager.groupsForMode( mode );
      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == type )
            groupsByType.push( groups[ i ] );

      // get the ordered keywords
      let keywords;

      // sort result
      groupsByType.sort( ( a, b ) =>
      {
         // sort image size first
         let asize = a.size.width * a.size.height;
         let bsize = b.size.width * b.size.height;
         if ( asize != bsize )
            return asize < bsize ? -1 : 1;

         // master file on bottom
         if ( a.hasMaster != b.hasMaster )
            return a.hasMaster ? -1 : 1;
         // filter by binning
         if ( a.binning != b.binning )
            return a.binning > b.binning ? -1 : 1;

         // for Flats, the filter is the only third sorting rule
         if ( type == ImageType.Flat )
            return a.filter.localeCompare( b.filter );

         // filter by duration
         if ( a.exposureTime != b.exposureTime )
            return a.exposureTime > b.exposureTime ? -1 : 1;

         // filter by filter name
         if ( a.filter != b.filter )
            return a.filter.localeCompare( b.filter );

         // allocate the sorting keywords only one time if needed
         if ( keywords == undefined )
            keywords = engine.keywords.sortedNames( mode );

         // filter by keywords
         for ( let j = 0; j < keywords.length; ++j )
         {
            let aKeyword = a.keywords[ keywords[ j ] ];
            let bKeyword = b.keywords[ keywords[ j ] ];
            if ( aKeyword != undefined && bKeyword == undefined )
               return -1;
            if ( aKeyword == undefined && bKeyword != undefined )
               return 1;
            if ( aKeyword != bKeyword )
               return aKeyword.localeCompare( bKeyword );
         }
         // sorting not defined, groups have the same sorting precedence (this should never happen)
         return 0;
      } );
      // resort inserting associated channels and recombined just after the master groups
      let sorted = [];
      // first pass, extract non associated groups and map the associated ones
      // linkedGroupIDmap is a map [groupID] => {R: group?, G: group?, B: group?...} mapping the groups
      // that have linked groups and the linked groups mapped on the associated channels, for a quick second pass insertion
      let linkedGroupIDmap = {};
      let parentGroups = [];
      for ( let i = 0; i < groupsByType.length; ++i )
      {
         let linkedGroupID = groupsByType[ i ].linkedGroupID;
         if ( linkedGroupID == undefined )
            parentGroups.push( groupsByType[ i ] );
         else
         {
            if ( !linkedGroupIDmap[ linkedGroupID ] )
               linkedGroupIDmap[ linkedGroupID ] = {}
            linkedGroupIDmap[ linkedGroupID ][ groupsByType[ i ].associatedRGBchannel ] = groupsByType[ i ];
         }
      }
      // second pass, insert the parents and the associated immediately after
      for ( let i = 0; i < parentGroups.length; ++i )
      {
         sorted.push( parentGroups[ i ] );
         let groupID = parentGroups[ i ].id;
         if ( linkedGroupIDmap[ groupID ] )
            for ( let j = 0; j < BPP.AssociatedChannel.sorted.length; ++j )
               if ( linkedGroupIDmap[ groupID ][ BPP.AssociatedChannel.sorted[ j ] ] )
                  sorted.push( linkedGroupIDmap[ groupID ][ BPP.AssociatedChannel.sorted[ j ] ] );
      }

      return sorted;
   }


   // ----------------------------------------------------------------------------
   // FRAME GROUP CHECKS
   // ----------------------------------------------------------------------------

   /**
    * Returns true if groups of the given type and mode exist.
    *
    * @param {ImageType} imageType
    * @param {WBPPGroupingMode} mode
    * @returns
    */
   hasFrames( imageType, mode )
   {
      let groups = this.groupsManager.groupsForMode( mode );
      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == imageType )
            return true;
      return false;
   }

   // ----------------------------------------------------------------------------

   /**
    * Returns true if bias frames exists.
    *
    * @returns
    */
   hasBiasFrames()
   {
      return this.hasFrames( ImageType.Bias, BPP.GroupingMode.PRE );
   }

   /**
    * Returns true if dark frames exists.
    *
    * @returns
    */
   hasDarkFrames()
   {
      return this.hasFrames( ImageType.Dark, BPP.GroupingMode.PRE );
   }

   /**
    * Returns true if flat frames exists.
    *
    * @returns
    */
   hasFlatFrames()
   {
      return this.hasFrames( ImageType.Flat, BPP.GroupingMode.PRE );
   }

   /**
    * Returns true if light frame groups exist for the specified mode.
    *
    * @param {WBPPGroupingMode} mode The grouping mode to check for light frames.
    * @returns {Boolean} True if light frame groups exist in the given mode, false otherwise.
    */
   hasLightFrames( mode )
   {
      return this.hasFrames( ImageType.Light, mode );
   }

   // ----------------------------------------------------------------------------
   // StackEngine Methods
   // ----------------------------------------------------------------------------

   /**
    * Returns the string describing the image type.
    *
    * @param {ImageType} imageType
    * @returns
    */
   static imageTypeToString( imageType )
   {
      return [ "Bias", "Dark", "Flat", "Light" ][ BPP.imageTypeIndex( imageType ) ];
   }

   // ----------------------------------------------------------------------------

   /**
    * Returns the string describing the master file associated to the provided image type.
    *
    * @param {ImageType} imageType
    * @returns
    */
   static imageTypeToMasterKeywordValue( imageType )
   {
      return [ "Master Bias", "Master Dark", "Master Flat", "Master Light" ][ BPP.imageTypeIndex( imageType ) ];
   }

   // ----------------------------------------------------------------------------

   /**
    * Shows the process logger dialog.
    */
   showProcessLogs()
   {
      let dialog = new ProcessLogDialog( this.processLogger );
      dialog.execute();
   }

   // ----------------------------------------------------------------------------

   /**
    * Removes all messages from the process logger.
    */
   cleanProcessLog()
   {
      this.processLogger.clean();
   }

   // ----------------------------------------------------------------------------
   // FILE ITEM MANAGEMENT
   // ----------------------------------------------------------------------------

   /**
    *  Finds the group matching the provided criteria. Virtual groups are excluded from the result.
    *
    * @param {ImageType} imageType
    * @param {String} filter
    * @param {Numeric} binning
    * @param {Numeric} exposureTime
    * @param {Object} size {width:Numeric, height:Numeric}
    * @param {Boolean} isMaster
    * @param {Boolean} isCFA
    * @param {Numeric} darkExposureTolerance
    * @param {Numeric} lightExposureTolerance
    * @param {{String: String}} keywords { key: value } keywords object
    * @param {Boolean} strictKeywordsMatching
    * @param {WBPPGroupingMode} mode
    * @returns
    */
   findGroup( imageType, filter, binning, exposureTime, size, isMaster, isCFA, darkExposureTolerance, lightExposureTolerance, keywords, strictKeywordsMatching, mode )
   {
      // memoization check to speed up the match
      let keywordsForMode = engine.keywords.filterKeywordsForMode( keywords, mode );
      let memoizationKey = "" + imageType + filter + binning + exposureTime + size.width + size.height + isMaster + isCFA + darkExposureTolerance + lightExposureTolerance + JSON.stringify( keywordsForMode ) + JSON.stringify( keywords ) + strictKeywordsMatching + mode;
      let memoizedGroup = engine.findGroupMemoization[ memoizationKey ];
      if ( memoizedGroup != undefined )
         return memoizedGroup;

      // NOTE: since there could be more than one group matching the same parameters but a different
      // number of keywords, we loop through all groups and we collect all groups that matches.
      // If there is more than one matching group then we do a final loop with the results and
      // we select the group that has the highest number of matching keywords
      let groupIndx = [];
      let groups = this.groupsManager.groupsForMode( mode );
      for ( let i = 0; i < groups.length; ++i )
      {
         // in case we're searching a group for a master frame then the tolerance is reduced to the maximum
         // precision in case the current group has a master too.
         // We do this because the tolerance has a meaning only when adding dark frames or matching
         // dark frame groups that contains only dark frames.
         let tolerance = isMaster ? BPP.Constants.MIN_EXPOSURE_TOLERANCE : darkExposureTolerance;
         if ( !groups[ i ].isVirtual() && groups[ i ].sameParameters( imageType, filter, binning, exposureTime, size, isCFA, tolerance, lightExposureTolerance, mode ) )
            groupIndx.push( i );
      }
      // return the group that best matches the keywords
      let bestGroupIndex = this.bestGroupMatchingKeywordsIndex( groups, exposureTime, groupIndx, keywordsForMode, strictKeywordsMatching );
      let group = bestGroupIndex == -1 ? undefined : groups[ bestGroupIndex ];
      engine.findGroupMemoization[ memoizationKey ] = group;
      return group;
   }

   // ----------------------------------------------------------------------------

   /**
    * Implements the strategy to select the best candidate group accordingly to the
    * provided keywords. If more than one group is found that matches the same number of
    * keywords then the groups are sorted following the keywords order and the
    * first gets selected. If the same keywords are matched from more than one group
    * then the group with the closest duration is selected
    *
    * @param {[FrameGroup]} groups
    * @param {Numeric} exposureTime the group exposure time
    * @param {Numeric} groupIndx indexes of candidate groups in groups array
    * @param {{String: String}} keywords { key: value } keywords object
    * @param {Boolean} strictKeywordsMatching if true keywords values must match exactly, including
    *                                         the keywords that have no values
    * @returns
    */
   bestGroupMatchingKeywordsIndex( groups, exposureTime, groupIndx, keywords, strictKeywordsMatching )
   {
      // return -1 if no group matches
      if ( groupIndx.length == 0 )
         return -1;
      // find the groups with the highest matching count
      let maxMatch = 0;
      let matchingIndexes = [];
      groupIndx.forEach( i =>
      {
         let matchCount = groups[ i ].keywordsMatchCount(
            keywords,
            strictKeywordsMatching, /* strictDirectMatching */
            strictKeywordsMatching /* strictInverseMatching */
         );

         if ( matchCount > maxMatch )
         {
            maxMatch = matchCount;
            matchingIndexes = [ i ];
         }
         else if ( matchCount == maxMatch )
            matchingIndexes.push( i );
      } );

      if ( matchingIndexes.length == 0 )
         return -1; // no matching groups

      if ( matchingIndexes.length == 1 )
         return matchingIndexes[ 0 ]; // one matching group

      // initialize an array with only the tied matching groups
      let groupsWithIndex = matchingIndexes.map( i => (
      {
         priority: 0,
         keywords: Object.keys( groups[ i ].keywords ),
         group: groups[ i ],
         index: i
      } ) );

      // update the index of a group
      engine.keywords.names().forEach( ( name, index ) =>
      {
         groupsWithIndex.forEach( ( g ) =>
         {
            if ( g.keywords.indexOf( name ) != -1 )
            {
               g.priority += 1 << ( index + 1 );
            }
         } );
      } );
      // return the group with the highest priority, and if there is a tie, the group with the closest exposure time
      groupsWithIndex.sort( ( a, b ) =>
      {
         if ( a.priority > b.priority )
            return -1;
         else if ( a.priority < b.priority )
            return 1;
         else
         {
            let A = Math.abs( a.group.exposureTime - exposureTime );
            let B = Math.abs( b.group.exposureTime - exposureTime );
            if ( A < B )
               return -1;
            else if ( A > B )
               return 1;
            else
               return 0;
         }
      } );

      return groupsWithIndex[ 0 ].index;
   }

   // ----------------------------------------------------------------------------
   /**
    * Returns the list of groups linked to the given parent group ID. Optionally,
    * a specified group can be excluded from the list.
    * @param {*} parentGroupID the parent group ID that all returned groups are linked to
    * @param {*} excludedGroup the group to be excluded from the returned list
    * @returns
    */
   getLinkedGroups( parentGroupID, excludedGroup )
   {
      // expect to find 3 linked groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );

      return groups.reduce( ( acc, group ) =>
         {
            if ( group.linkedGroupID == parentGroupID )
               if ( excludedGroup == undefined || ( group.id != excludedGroup.id ) )
                  acc.push( group );
            return acc;
         },
         [] );
   }

   // ----------------------------------------------------------------------------

   /**
    * Performs a sanity check on the file at the given filePath.
    *
    * @param {String} filePath
    * @returns
    */
   checkFile( filePath )
   {
      // path must not be an empty string
      if ( WBPPUtils.isEmptyString( filePath ) )
         return {
            success: false,
            message: "Empty file path"
         };

      // file must exist
      if ( !File.exists( filePath ) )
         return {
            success: false,
            message: "File not found: " + filePath
         }

      // file must not be already added. By default the grouping mode WBPPGroupingMode = .pre is used for this check
      let groups = this.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      for ( let i = 0; i < groups.length; ++i )
         for ( let j = 0; j < groups[ i ].fileItems.length; ++j )
            if ( groups[ i ].fileItems[ j ].filePath == filePath )
               return {
                  success: false,
                  message: "File " + filePath + " has already been added as " + StackEngine.imageTypeToString( groups[ i ].imageType ) + " frame"
               }

      return {
         success: true
      };
   }

   // ----------------------------------------------------------------------------
   /**
    * Resets the automatic fast imaging mode groups.
    *
    * This function resets the list of the automatic fast imaging mode groups.
    * It is used to list the groups for which FastImaging has been automatically activated
    * when many frame items have been added to those groups.
    */
   resetAutomaticFastImagingModeGroups()
   {
      this.automaticFIgroups = [];
   }

   // ----------------------------------------------------------------------------

   findFileInSearchPath( filePath )
   {
      if ( this.fileSearchRootPath == undefined || typeof this.fileSearchRootPath != "string" || this.fileSearchRootPath.length == 0 )
         return undefined;

      let pathComponents = filePath.split( "/" );
      for ( let i = 0; i < pathComponents.length; i++ )
      {
         let searchPath = this.fileSearchRootPath + "/" + pathComponents.slice( i ).join( "/" );
         if ( File.exists( searchPath ) )
            return searchPath;
      }
      return undefined;
   }

   /**
    * Adds a new file with the given properties.
    *
    * @param {String} filePath
    * @param {ImageType} imageType
    * @param {String} filter
    * @param {Numeric} binning
    * @param {Numeric} exposureTime
    * @param {Object} overrideSize {width: Numeric, height: Numeric}, optional
    * @param {Boolean} overrideCFA
    * @param {*} customModes
    * @param {Boolean} [overrideSmartNaming] - When provided, overrides engine.smartNamingOverride
    *        for this file. Used during reconstruction from saved settings to preserve the
    *        per-file frozen smartNamingOverride state (createdWithSmartNamingEnabled).
    * @returns
    */
   addFile( filePath, imageType, filter, binning, exposureTime, overrideSize, overrideCFA, customModes, overrideSmartNaming )
   {
      filePath = filePath.trim();

      // check if the file exists and is valid, return success: false if not
      let checkResult = engine.checkFile( filePath );
      if ( !checkResult.success )
      {
         if ( engine.fileSearchRootPath && engine.fileSearchRootPath != "" )
         {
            // in automation mode we may have to find the file looking into the fileSarchRootPath
            // The startegy is to match the file
            filePath = engine.findFileInSearchPath( filePath )
            if ( !filePath )
            {
               return {
                  success: false,
                  message: "File not found"
               };
            }
         }
         else
            return checkResult;
      }

      let smartNaming = ( overrideSmartNaming != null ) ? overrideSmartNaming : engine.smartNamingOverride;
      let fileInfo = WBPPUtils.keywords.readFileInfos( filePath, this.imageProcessor.inputHints(), smartNaming );
      if ( !fileInfo.success )
         return fileInfo;

      // --------------------------------------------------------------------------
      // quick check to reject files with invalid dimensions and master files that
      // are not XISF files
      // --------------------------------------------------------------------------

      if ( overrideSize !== undefined && overrideSize !== null )
      {
         fileInfo.size.width = overrideSize.width;
         fileInfo.size.height = overrideSize.height;
      }
      if ( fileInfo.size.width === null || fileInfo.size.height === null
         || fileInfo.size.width === undefined || fileInfo.size.height === undefined
         || fileInfo.size.width <= 0 || fileInfo.size.height <= 0 )
         return {
            success: false,
            message: "Unable to detect image dimensions"
         };

      // --------------------------------------------------------------------------
      // force some parameters if provided by the caller
      // --------------------------------------------------------------------------

      if ( imageType !== undefined && imageType !== null && imageType != ImageType.Unknown )
         fileInfo.imageType = imageType;

      if ( filter !== undefined && filter !== null && filter != "" && filter != "?" )
         fileInfo.filter = filter;

      if ( binning !== undefined && binning !== null && binning > 0 )
         fileInfo.binning = binning;

      if ( exposureTime !== undefined && exposureTime !== null && exposureTime > 0 )
         fileInfo.exposureTime = exposureTime;
      if ( (fileInfo.exposureTime !== null && fileInfo.exposureTime < 0) || imageType == ImageType.Bias )
         fileInfo.exposureTime = 0;

      if ( overrideCFA !== undefined && overrideCFA !== null )
         fileInfo.isCFA = !!overrideCFA;
      else
         fileInfo.isCFA = fileInfo.bayerpat !== null;

      // --------------------------------------------------------------------------
      // initialize the solver parameters
      // --------------------------------------------------------------------------

      let solverParams = {
         observationDate: fileInfo.observationDate,
         timestamp: fileInfo.timestamp,
         ra: NaN,
         dec: NaN,
         pixelSize: NaN,
         focalLength: NaN
      };

      if ( fileInfo.centerRA !== null && isFinite( fileInfo.centerRA ) )
         solverParams.ra = fileInfo.centerRA;

      if ( fileInfo.centerDec !== null && isFinite( fileInfo.centerDec ) )
         solverParams.dec = fileInfo.centerDec;

      if ( fileInfo.pixelSize !== null && isFinite( fileInfo.pixelSize ) )
         solverParams.pixelSize = fileInfo.pixelSize;

      if ( fileInfo.focalLength !== null && isFinite( fileInfo.focalLength ) )
         solverParams.focalLength = fileInfo.focalLength;

      // --------------------------------------------------------------------------
      // read some metadata form the file path if still not defined
      // --------------------------------------------------------------------------

      if ( fileInfo.imageType == ImageType.Unknown )
      {
         fileInfo.imageType = WBPPUtils.smartNaming.getImageTypeFromPath( filePath );
         if ( fileInfo.imageType == ImageType.Unknown )
         {
            this.diagnosticMessages.push( "Unable to determine frame type; assuming LIGHT frame: " + filePath );
            fileInfo.imageType = ImageType.Light;
            fileInfo.isMaster = false;
         }
      }

      if ( !fileInfo.isMaster && engine.detectMasterIncludingFullPath )
         fileInfo.isMaster = ( imageType == ImageType.Light ) ? false : WBPPUtils.smartNaming.isMasterFromPath( filePath );

      // Reject any master file which does not have a .xisf extension
      if ( fileInfo.isMaster && File.extractExtension( filePath ).toLowerCase() != ".xisf" )
         return {
            success: false,
            message: ( "Master file " + filePath + " rejected: master calibration files must be in XISF format." )
         };

      if ( fileInfo.binning === null )
         fileInfo.binning = WBPPUtils.smartNaming.getBinningFromPath( filePath );
      if ( fileInfo.filter === null )
         fileInfo.filter = WBPPUtils.smartNaming.getFilterFromPath( filePath ) || "NoFilter";
      if ( fileInfo.exposureTime === null )
         fileInfo.exposureTime = WBPPUtils.smartNaming.getExposureTimeFromPath( filePath );

      // set the custom matching sizes for the master flat
      let matchingSizes = {};
      if ( fileInfo.isMaster && fileInfo.imageType == ImageType.Flat && fileInfo.preovscw !== null && fileInfo.preovsch !== null )
         matchingSizes[ BPP.GroupingMode.PRE ] = {
            width: fileInfo.preovscw,
            height: fileInfo.preovsch
         };

      let fileKeywords = {};
      for ( let i = 0; i < fileInfo.keywords.length; ++i )
      {
         let name = fileInfo.keywords[ i ].name;
         if ( name != "HISTORY" )
         {
            let value = fileInfo.keywords[ i ].strippedValue;
            fileKeywords[ name ] = value;
         }
      }

      let item = new FileItem( filePath,
         fileInfo.imageType,
         fileInfo.filter,
         fileInfo.binning,
         fileInfo.exposureTime,
         fileKeywords,
         fileInfo.size,
         matchingSizes,
         fileInfo.isCFA,
         fileInfo.isMaster,
         undefined, /* item keywords are not defined yet */
         solverParams,
         fileInfo.overscan );

      // Override the frozen smart naming state with the resolved value.
      // This matters when reconstructing from saved settings where the
      // per-file frozen value is passed via overrideSmartNaming.
      item.createdWithSmartNamingEnabled = smartNaming;

      // once created we can update the keywords
      item.updateKeywords();

      this.groupsManager.addFileItem( item, undefined /* custom keywords */ , customModes );

      return {
         success: true
      };
   }

   // ----------------------------------------------------------------------------

   /**
    * Adds a bias Frame.
    *
    * @param {String} filePath
    * @returns
    */
   addBiasFrame( filePath )
   {
      return this.addFile( filePath, ImageType.Bias );
   }

   // ----------------------------------------------------------------------------

   /**
    * Adds a dark frame.
    *
    * @param {String} filePath
    * @returns
    */
   addDarkFrame( filePath )
   {
      return this.addFile( filePath, ImageType.Dark );
   }

   // ----------------------------------------------------------------------------

   /**
    * Adds a flat frame.
    *
    * @param {String} filePath
    * @returns
    */
   addFlatFrame( filePath )
   {
      return this.addFile( filePath, ImageType.Flat );
   }

   // ----------------------------------------------------------------------------

   /**
    * Adds a light frame.
    *
    * @param {String} filePath
    * @returns
    */
   addLightFrame( filePath )
   {
      return this.addFile( filePath, ImageType.Light );
   }

   // ----------------------------------------------------------------------------
   /**
    * Rebuilds groups and regenerate the execution pipeline.
    *
    */
   rebuild()
   {
      // engine rebuild is always performed with in-memory data
      this.reconstructGroups( true /* from cache */ );
      this.pipelineManager.buildExecutionPipeline();
   }

   /**
    * Reconstruction is performed by scanning all files in pre-processing groups
    * and re-add them one by one. Before reconstructing, all properties for each
    * group is saved and after the reconstruction the properties are restored
    * if groups with same ID have been created.
    *
    * @param {*} formCache true if file item properties have to be read from memory
    *                      instead of being read from disk.
    */
   reconstructGroups( fromCache )
   {
      // reset the memoization cache
      engine.findGroupMemoization = {};

      // clean up null values
      this.removePurgedElements();

      // save the current group properties to be restored for the unchanged groups
      this.groupsManager.cacheGroupsProperties();

      // get all groups in pre-processing state, these contain all files added to WBPP
      let fileItems = {};
      let groups = this.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      // flatten files, ensure uniqueness
      let filePaths = [];
      for ( let i = 0; i < groups.length; ++i )
         for ( let j = 0; j < groups[ i ].fileItems.length; ++j )
         {
            let fileItem = groups[ i ].fileItems[ j ];
            // ensure uniqueness
            if ( fileItems[ fileItem.filePath ] == undefined )
            {
               // first add the masters then add the other files
               if ( fileItem.isMaster )
                  filePaths.unshift( fileItem.filePath );
               else
                  filePaths.push( fileItem.filePath );
               fileItems[ fileItem.filePath ] = fileItem;
            }
         }

      // remove all groups
      this.groupsManager.clear();

      // re-add files one by one
      for ( let i = 0; i < filePaths.length; ++i )
      {
         let filePath = filePaths[ i ];
         let fileItem = fileItems[ filePath ];
         if ( fileItem )
         {
            if ( fromCache )
            {
               // update the keywords in case they have changed
               fileItem.updateKeywords();
               this.groupsManager.addFileItem( fileItem, undefined /* custom keywords */ , [ BPP.GroupingMode.PRE ] /* customModes */ );
            }
            else
            {
               this.addFile(
                  fileItem.filePath,
                  fileItem.imageType,
                  fileItem.filter,
                  fileItem.binning,
                  fileItem.exposureTime,
                  fileItem.size,
                  undefined, /* override CFA */
                  [ BPP.GroupingMode.PRE ], /* customModes */
                  fileItem.createdWithSmartNamingEnabled /* overrideSmartNaming */
               );
            }
         }
      }

      // ready to restore the group properties
      this.groupsManager.restoreGroupsPropertiesFromCache( BPP.GroupingMode.PRE );

      // reconstruct post process groups after PRE has been completed
      this.reconstructPostProcessGroups();

      // ready to restore the group properties
      this.groupsManager.restoreGroupsPropertiesFromCache( BPP.GroupingMode.POST );

      // we need to know which frames will belong to post-calibration groups
      // integrated with fast integration data. This
      this.updateFastIntegrationData();

      // sort files by name
      this.groupsManager.groups.forEach( g =>
      {
         if ( g.mode == BPP.GroupingMode.PRE )
         {
            // sort but keep the master file in first position
            let master;
            if ( g.hasMaster )
            {
               master = g.fileItems[ 0 ];
               g.fileItems.shift();
            }
            g.fileItems.sort( ( a, b ) =>
            {
               return a.filePath.localeCompare( b.filePath );
            } )
            if ( master )
            {
               g.fileItems.unshift( master );
            }
         }
      } );

      // aux: returns the list of groups with the given type and mode, adding the
      // counter property
      let _getGroups = ( type, mode ) =>
      {
         // get the list of sorted groups
         let groups = engine.getSortedGroupsOfType( type, mode );
         // add the counter property (GUI purposes)
         groups.forEach( ( g, i ) =>
         {
            g.__counter__ = i + 1;
         } );
         return groups;
      }

      // sorted groups
      let bias = _getGroups( ImageType.Bias, BPP.GroupingMode.PRE );
      let dark = _getGroups( ImageType.Dark, BPP.GroupingMode.PRE );
      let flat = _getGroups( ImageType.Flat, BPP.GroupingMode.PRE );
      let light_pre = _getGroups( ImageType.Light, BPP.GroupingMode.PRE );
      let light_post = _getGroups( ImageType.Light, BPP.GroupingMode.POST );
      // clear and re-add groups in sorted order
      this.groupsManager.clear();
      bias.forEach( g => this.groupsManager.groups.push( g ) );
      dark.forEach( g => this.groupsManager.groups.push( g ) );
      flat.forEach( g => this.groupsManager.groups.push( g ) );
      light_pre.forEach( g => this.groupsManager.groups.push( g ) );
      light_post.forEach( g => this.groupsManager.groups.push( g ) );
   } /** StackEngine.prototype.reconstructGroups */

   /**
    * Reconstruction is performed by scanning all files in pre-processing groups
    * and re-add them one by one. Before reconstructing, all properties for each
    * group is saved and after the reconstruction the properties are restored
    * if groups with same ID have been created.
    */
   reconstructPostProcessGroups()
   {
      // clean up null values
      this.removePurgedElements();

      // get all groups in pre-processing state, these contain all files added to WBPP
      let fileItems = [];
      let preGroups = this.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      // flatten files and store the overridden CFA property
      for ( let i = 0; i < preGroups.length; ++i )
         if ( preGroups[ i ].imageType == ImageType.Light )
         {
            for ( let j = 0; j < preGroups[ i ].fileItems.length; ++j )
               fileItems.push(
               {
                  fileItem: preGroups[ i ].fileItems[ j ],
                  isCFA: preGroups[ i ].isCFA
               } );
         }

      // purge post-process groups
      let postGroups = this.groupsManager.groupsForMode( BPP.GroupingMode.POST );
      postGroups.forEach( g =>
      {
         g.__purged__ = true;
      } );
      this.removePurgedElements();

      // re-add file items one by one.
      for ( let i = 0; i < fileItems.length; ++i )
      {
         let fileItem = fileItems[ i ].fileItem;
         if ( fileItem )
         {
            // override the POST matching size depending on the overscan settings
            if ( this.overscan.enabled )
            {
               fileItem.matchingSizes[ BPP.GroupingMode.POST ] = {
                  width: engine.overscan.imageRect.x1 - engine.overscan.imageRect.x0,
                  height: engine.overscan.imageRect.y1 - engine.overscan.imageRect.y0
               }
            }
            else
               fileItem.matchingSizes[ BPP.GroupingMode.POST ] = fileItem.matchingSizes[ BPP.GroupingMode.PRE ];

            let isCFA = fileItems[ i ].isCFA;
            this.groupsManager.addFileItem(
               fileItem,
               undefined /* custom keywords */ ,
               [ BPP.GroupingMode.POST ],
               isCFA /* custom CFA */
            );
         }
      }

      // retrieve the groups again and insert the associated groups for the separated RGB channels
      let updatedPostGroups = this.groupsManager.groups.reduce( ( acc, group ) =>
      {
         // let preprocessing groups unchanged
         if ( group.mode == BPP.GroupingMode.PRE )
         {
            acc.push( group );
            return acc;
         }

         // POST processing group: if the group is CFA then it remains if the debayer mode is combined RGB channels or both
         if ( !group.isCFA || this.debayerOutputMethod == BPP.DebayerOutputMode.COMBINED )
         {
            acc.push( group );
            return acc;
         }

         // hide and deactivate the post RGB group if only the separated RGB channels are generated

         if ( this.debayerOutputMethod == BPP.DebayerOutputMode.SEPARATED )
         {
            group.isHidden = true;
            group.isActive = false;
         }
         acc.push( group );
         let associatedChannels = [];
         if ( engine.debayerActiveChannelR )
            associatedChannels.push( BPP.AssociatedChannel.R );
         if ( engine.debayerActiveChannelG )
            associatedChannels.push( BPP.AssociatedChannel.G );
         if ( engine.debayerActiveChannelB )
            associatedChannels.push( BPP.AssociatedChannel.B );

         associatedChannels.forEach( associatedRGBchannel =>
         {
            let associatedGroup = new FrameGroup(
               group.imageType,
               group.filter,
               group.binning,
               group.exposureTime,
               group.size,
               false, // isCFA: group is managed as MONO
               null, // firstItem: group is initially empty
               false, // hasMaster
               group.keywords,
               group.mode,
               associatedRGBchannel,
               group.id, // the parent linked group
               undefined, // drizzle data
               undefined, // fast integration data
               undefined // cosmetic correction data
            );
            associatedGroup.exposureTimes = group.exposureTimes.slice();
            // associate the same files, the function "activeFrames()" will return the associated file paths
            // for the given RGB channel
            associatedGroup.fileItems = group.fileItems;
            acc.push( associatedGroup );
         } );

         // recombination is performed only if all channels are active
         if ( engine.recombineRGB && associatedChannels.length == 3 && engine.integrate )
         {
            let associatedGroup = new FrameGroup(
               group.imageType,
               group.filter,
               group.binning,
               group.exposureTime,
               group.size,
               true, /* isCFA: group is managed as CFA */
               null, /* firstItem: group is initially empty */
               false, /* hasMaster */
               group.keywords,
               group.mode,
               BPP.AssociatedChannel.COMBINED_RGB,
               group.id /* the parent linked group */
            );
            associatedGroup.isHidden = false;
            associatedGroup.exposureTimes = group.exposureTimes.slice();
            acc.push( associatedGroup );
         }

         return acc;
      }, [] );

      this.groupsManager.groups = updatedPostGroups;
   }

   // ----------------------------------------------------------------------------

   /**
    * Propagates the information about fast integration into the file items.
    * To schedule an optimized pipeline we need to know if a file item
    * belongs to a post-calibration group integrated with fast integration.
    */
   updateFastIntegrationData()
   {
      let groups = this.groupsManager.groupsForMode( BPP.GroupingMode.POST );
      for ( let i = 0; i < groups.length; ++i )
      {
         let fileItems = groups[ i ].fileItems;
         let fi = groups[ i ].fastIntegrationData.enabled;
         for ( let j = 0; j < fileItems.length; ++j )
         {
            let value = fileItems[ j ].__fastIntegration;
            fileItems[ j ].__fastIntegration = ( value || true ) & fi;
         }
      }
   }

   // ----------------------------------------------------------------------------

   rejectionNames()
   {
      return StackEngine.rejectionMethods.map( item => item.name );
   }

   // ----------------------------------------------------------------------------

   rejectionFromIndex( index )
   {
      return StackEngine.rejectionMethods[ index ].rejection;
   }

   // ----------------------------------------------------------------------------

   rejectionName( rejection )
   {
      for ( let i = 0; i < StackEngine.rejectionMethods.length; ++i )
         if ( StackEngine.rejectionMethods[ i ].rejection === rejection )
            return StackEngine.rejectionMethods[ i ].name;
      return StackEngine.rejectionMethods[ StackEngine.rejectionMethods.length - 1 ].name;
   }

   // ----------------------------------------------------------------------------

   rejectionIndex( rejection )
   {
      for ( let i = 0; i < StackEngine.rejectionMethods.length; ++i )
         if ( StackEngine.rejectionMethods[ i ].rejection === rejection )
            return i;
      return StackEngine.rejectionMethods.length - 1;
   }

   // ----------------------------------------------------------------------------

   /**
    * Cleans up elements that has been deallocated but that are still in the groups
    * or file items lists.
    *
    */
   removePurgedElements()
   {
      let groups = this.groupsManager.groups;
      for ( let i = groups.length; --i >= 0; )
      {
         if ( !groups[ i ] || groups[ i ].__purged__ )
            this.groupsManager.removeGroupAtIndex( i );
         else
         {
            for ( let j = groups[ i ].fileItems.length; --j >= 0; )
               if ( !groups[ i ].fileItems[ j ] || groups[ i ].fileItems[ j ].__purged__ )
                  groups[ i ].removeItem( j );
            if ( groups[ i ].fileItems.length == 0 )
               this.groupsManager.removeGroupAtIndex( i );
         }
      }
   }
}

// ----------------------------------------------------------------------------

StackEngine.rejectionMethods = [
{
   name: "Percentile Clipping",
   rejection: ImageIntegration.PercentileClip
},
{
   name: "Winsorized Sigma Clipping",
   rejection: ImageIntegration.WinsorizedSigmaClip
},
{
   name: "Linear Fit Clipping",
   rejection: ImageIntegration.LinearFit
},
{
   name: "Generalized Extreme Studentized Deviate",
   rejection: ImageIntegration.Rejection_ESD
},
{
   name: "Robust Chauvenet Rejection",
   rejection: ImageIntegration.Rejection_RCR
},
{
   name: "Auto",
   rejection: BPP.REJECTION_AUTO
} ];

// ----------------------------------------------------------------------------

StackEngine.prototype.defaults = {
   globals: () =>
   {},
   overscan: () =>
   {
      for ( let i = 0; i < 4; ++i )
      {
         engine.overscan.overscan[ i ].enabled = false;
         engine.overscan.overscan[ i ].sourceRect.assign( 0 );
         engine.overscan.overscan[ i ].targetRect.assign( 0 );
      }
      engine.overscan.imageRect.assign( 0 );
   },
   customFormulaWeights: () =>
   {
      engine.subframeWeightingPreset = BPP.Defaults.subframeweightingPreset;
      engine.FWHMWeight = BPP.Defaults.subframeweightingFwhmWeight;
      engine.eccentricityWeight = BPP.Defaults.subframeweightingEccentricityWeight;
      engine.starsWeight = BPP.Defaults.subframeweightingStarsWeight;
      engine.PSFSignalWeight = BPP.Defaults.subframeweightingPsfSignalWeight;
      engine.PSFSNRWeight = BPP.Defaults.subframeweightingPsfSnrWeight;
      engine.SNRWeight = BPP.Defaults.subframeweightingSnrWeight;
      engine.pedestal = BPP.Defaults.subframeweightingPedestal;
   },
   imageRegistration: () =>
   {
      engine.pixelInterpolation = BPP.Defaults.saPixelInterpolation;
      engine.clampingThreshold = BPP.Defaults.saClampingThreshold;
      engine.maxStars = BPP.Defaults.saMaxStars;
      engine.distortionCorrection = BPP.Defaults.saDistortionCorrection;
      engine.maxSplinePoints = BPP.Defaults.saMaxSplinePoints;
      engine.rigidTransformations = BPP.Defaults.saRigidTransformations;
      engine.structureLayers = BPP.Defaults.saStructureLayers;
      engine.minStructureSize = BPP.Defaults.saMinStructureSize;
      engine.hotPixelFilterRadius = BPP.Defaults.saHotPixelFilterRadius;
      engine.noiseReductionFilterRadius = BPP.Defaults.saNoiseReduction;
      engine.sensitivity = BPP.Defaults.saSensitivity;
      engine.peakResponse = BPP.Defaults.saPeakResponse;
      engine.brightThreshold = BPP.Defaults.saBrightThreshold;
      engine.maxStarDistortion = BPP.Defaults.saMaxStarDistortion;
      engine.allowClusteredSources = BPP.Defaults.saAllowClusteredSources;
      engine.useTriangleSimilarity = BPP.Defaults.saUseTriangleSimilarity;
      engine.reuseLastReferenceFrames = BPP.Defaults.saDefaultReuseLastReferenceFrames;
   },
   imageSolver: () =>
   {
      engine.imageSolverRa = BPP.Defaults.imageSolverRa;
      engine.imageSolverDec = BPP.Defaults.imageSolverDec;
      engine.imageSolverObservationTime = BPP.Defaults.imageSolverObservationTime;
      engine.imageSolverFocalLength = BPP.Defaults.imageSolverFocalLength;
      engine.imageSolverPixelSize = BPP.Defaults.imageSolverPixelSize;
      engine.imageSolverForceDefaults = BPP.Defaults.imageSolverForceDefaults;
   },
   localNormalization: () =>
   {
      engine.localNormalization = BPP.Defaults.localnormalization;
      engine.localNormalizationInteractiveMode = BPP.Defaults.localnormalizationInteractiveMode;
      engine.localNormalizationGenerateImages = BPP.Defaults.localnormalizationGenerateImages;
      engine.localNormalizationMethod = BPP.Defaults.localnormalizationMethod;
      engine.localNormalizationMaxIntegratedFrames = BPP.Defaults.localnormalizationIntegratedFrames;
      engine.localNormalizationBestReferenceSelectionMethod = BPP.Defaults.localnormalizationBestReferenceMethod;
      engine.localNormalizationGridSize = BPP.Defaults.localnormalizationGridSize;
      engine.localNormalizationReferenceFrameGenerationMethod = BPP.Defaults.localnormalizationRefFrameMethod;
      engine.localNormalizationPsfType = BPP.Defaults.localnormalizationPsfType;
      engine.localNormalizationPsfGrowth = BPP.Defaults.localnormalizationPsfGrowth;
      engine.localNormalizationPsfMaxStars = BPP.Defaults.localnormalizationPsfMaxStars;
      engine.localNormalizationPsfMinSNR = BPP.Defaults.localnormalizationPsfMinSnr;
      engine.localNormalizationPsfAllowClusteredSources = BPP.Defaults.localnormalizationPsfAllowClustered;
      engine.localNormalizationLowClippingLevel = BPP.Defaults.localnormalizationLowClippingLevel;
      engine.localNormalizationHighClippingLevel = BPP.Defaults.localnormalizationHighClippingLevel;
      engine.reuseLastLNReferenceFrames = BPP.Defaults.localnormalizationReuseReferenceFrame;
   },
   frameSelectionFilters: () =>
   {
      engine.frameSelectionDefaultConfig = [
         { enabled: false, key: "FWHM", value: 0, compareMode: FrameFilterCompareMode.LESS_THAN },
         { enabled: false, key: "eccentricity", value: 0, compareMode: FrameFilterCompareMode.LESS_THAN },
         { enabled: false, key: "PSFSignalWeight", value: 0, compareMode: FrameFilterCompareMode.GREATER_THAN },
         { enabled: false, key: "median", value: 0, compareMode: FrameFilterCompareMode.GREATER_THAN },
         { enabled: false, key: "numberOfStars", value: 0, compareMode: FrameFilterCompareMode.GREATER_THAN },
         { enabled: false, key: "custom", value: 0, compareMode: FrameFilterCompareMode.GREATER_THAN, isCustomFormula: true, formula: "" }
      ];
   },
   imageIntegration: ( imageType ) =>
   {
      let idx = BPP.imageTypeIndex( imageType );
      engine.combination[ idx ] = ImageIntegration.Average;
      engine.rejection[ idx ] = BPP.Defaults.rejectionMethod;
      engine.percentileLow[ idx ] = 0.2;
      engine.percentileHigh[ idx ] = 0.1;
      engine.sigmaLow[ idx ] = 4.0;
      engine.sigmaHigh[ idx ] = 3.0;
      engine.linearFitLow[ idx ] = 5.0;
      engine.linearFitHigh[ idx ] = 3.5;
      engine.ESD_Outliers[ idx ] = 0.3;
      engine.ESD_Significance[ idx ] = 0.05;
      engine.RCR_Limit[ idx ] = 0.1;

      if ( imageType == ImageType.Flat )
      {
         engine.flatsLargeScaleRejection = BPP.Defaults.largeScaleRejection;
         engine.flatsLargeScaleRejectionLayers = BPP.Defaults.largeScaleLayers;
         engine.flatsLargeScaleRejectionGrowth = BPP.Defaults.largeScaleGrowth;
      }

      if ( imageType == ImageType.Light )
      {
         engine.minWeight = BPP.Defaults.minWeight;
         engine.lightsLargeScaleRejectionHigh = BPP.Defaults.largeScaleRejection;
         engine.lightsLargeScaleRejectionLayersHigh = BPP.Defaults.largeScaleLayers;
         engine.lightsLargeScaleRejectionGrowthHigh = BPP.Defaults.largeScaleGrowth;
         engine.lightsLargeScaleRejectionLow = BPP.Defaults.largeScaleRejection;
         engine.lightsLargeScaleRejectionLayersLow = BPP.Defaults.largeScaleLayers;
         engine.lightsLargeScaleRejectionGrowthLow = BPP.Defaults.largeScaleGrowth;
      }
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-StackEngine.js - Released 2026-05-10T11:05:00Z
