// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-CalibrationMatcher.js - Released 2026-05-10T11:05:00Z
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

var CalibrationMatcher = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   // ........................................................................

   /**
    * Sets the global overscan settings from a specific group settings.
    *
    * @param {*} group the group containing the overscan settings
    */
   setOverscanInfoFromGroup( group )
   {
      if ( group.hasMaster )
         this.engine.overscan.copyFrom( group.fileItems[ 0 ].overscan );
   }

   // ........................................................................

   /**
    * Search for the groups that are calibrated by the provided group.
    * NB: by default this function looks the calibration groups with mode WBPPGroupingMode = .PRE
    *
    * @param {FrameGroup} group the group that calibrates all the returned groups
    * @returns the array of groups that are calibrated by the provided group
    */
   getGroupsCalibratedBy( group )
   {
      let calibratedBy = [];

      // Scan all pre-processing groups, search for the calibration files for each group
      // of the same type of the provided group, if the ID matches then the looped group
      // is calibrated with the provided file
      let groups = this.engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      for ( let i = 0; i < groups.length; ++i )
      {
         let cg = groups[ i ];

         if ( cg == group )
            continue;

         let cf = this.getCalibrationGroupsFor( cg );

         if ( group.imageType == ImageType.Bias && group == cf.masterBias )
         {
            calibratedBy.push( cg );
            continue
         }

         if ( group.imageType == ImageType.Dark && group == cf.masterDark )
         {
            calibratedBy.push( cg );
            continue
         }

         if ( group.imageType == ImageType.Flat && group == cf.masterFlat )
         {
            calibratedBy.push( cg );
            continue
         }
      }
      return calibratedBy;
   }

   // ........................................................................

   /**
    * Search for the groups that calibrate the provided group.
    *
    * @param {FrameGroup} group the group for which we want to retrieve the calibration groups
    * @returns {{masterBias: FrameGroup|undefined, masterDark: FrameGroup|undefined, masterFlat: FrameGroup|undefined}} object containing the matching calibration groups
    */
   getCalibrationGroupsFor( group )
   {
      let calibrationGroups = {
         masterBias: undefined,
         masterDark: undefined,
         masterFlat: undefined,
      };
      // a master file is not calibrated
      if ( group.hasMaster )
         return calibrationGroups;

      let mb, md, mf;
      let size = group.size;
      let binning = group.binning;
      let exposureTime = group.exposureTime;
      let filter = group.filter;
      let exactDarkExposureTime = false;
      let isCFA = group.isCFA;

      switch ( group.imageType )
      {
         case ImageType.Dark:
            // dark frames are never calibrated
            break;
         case ImageType.Flat:
            // look for compatible master dark and master bias
            mb = this.getMasterBiasGroup( binning, size, false /*isMaster*/ , group.keywords );
            if ( !group.forceNoDark )
               md = group.overrideDark || this.getMasterDarkGroup( ImageType.Flat, binning, exposureTime, size, mb /* exactDarkExposureTime: yes if we have a master bias */ , group.keywords );
            break;
         case ImageType.Light:
            mb = this.getMasterBiasGroup( binning, size, false, group.keywords );
            if ( !group.forceNoDark )
               md = group.overrideDark || this.getMasterDarkGroup( ImageType.Light, binning, exposureTime, size, exactDarkExposureTime, group.keywords );
            if ( !group.forceNoFlat )
               mf = group.overrideFlat || this.getMasterFlatGroup( binning, size, filter, isCFA, false /*isMaster*/ , group.keywords );
            break;
      }

      // Advanced logic: remove master bias when it is not necessary.
      // MasterBias is needed only when:
      // 1. master dark is NOT present
      // 2. master dark is present and optimized
      // Note: if the master dark does not contain the bias signal, the user is
      // responsible for configuring the calibration setup accordingly.
      if ( mb )
      {
         let masterDarkIsNotPresent = !md;
         let masterDarkIsOptimized = md && group.optimizeMasterDark;

         if ( masterDarkIsNotPresent || masterDarkIsOptimized )
            calibrationGroups.masterBias = mb;
      }
      if ( md )
         calibrationGroups.masterDark = md;
      if ( mf )
         calibrationGroups.masterFlat = mf;

      return calibrationGroups;
   }

   // ........................................................................

   /**
    * Returns an array of { group, count } objects containing a group and the number
    * of matching keywords, filtering by the image type provided.
    * For each group, the number of matching keywords is counted, groups with the same
    * count are grouped together and the groups with the same keyword matching count is
    * sorted by keyword precedence.
    *
    * @param {ImageType} imageType
    * @param {Object} size {width:Numeric, height:Numeric}
    * @param {{String:String}} keywords the keywords key-value map
    * @param {Boolean} onlyHighestMatches if true returns the list of groups with the
    *                                     highest number of matching keywords, otherwise
    *                                     it returns all the matching groups
    * @returns {Array<{group: FrameGroup, count: number}>} sorted list of compatible groups with their keyword match counts
    */
   getCompatibleCalibrationGroups( imageType, size, keywords, onlyHighestMatches )
   {
      let engine = this.engine;

      // preselect the compatible groups
      let matchingGroups = {};
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == imageType )
         {
            // overscan handling: when we search for a group with overscan enabled we have to handle the case
            // where a flat group has a master into it, then the master size must match the current overscan
            // area size to match, otherwise the regular matching is applied
            let compatibleSize = groups[ i ].size.width == size.width && groups[ i ].size.height == size.height;
            if ( imageType == ImageType.Flat
               && groups[ i ].hasMaster )
            {
               if ( engine.overscan.enabled )
               {
                  // in case of overscan is enabled then also the size of the master must match the size of the overscan area
                  let W = engine.overscan.imageRect.x1 - engine.overscan.imageRect.x0;
                  let H = engine.overscan.imageRect.y1 - engine.overscan.imageRect.y0;
                  compatibleSize = compatibleSize && groups[ i ].fileItems[ 0 ].size.width == W && groups[ i ].fileItems[ 0 ].size.height == H;
               }
               else
               {
                  // in case of overscan is not active then the size of the master must match the provided size
                  compatibleSize = compatibleSize && groups[ i ].fileItems[ 0 ].size.width == size.width && groups[ i ].fileItems[ 0 ].size.height == size.height;
               }
            }

            if ( compatibleSize )
            {
               // enable the strict direct matching i.e. we exclude a group if it
               // has a keyword that is not in the set of the provided keywords
               let count = groups[ i ].keywordsMatchCount(
                  keywords,
                  true, /* strictDirectMatching */
                  false /* strictInverseMatching */
               );
               if ( count >= 0 )
               {
                  if ( !matchingGroups[ count ] )
                     matchingGroups[ count ] = [];
                  matchingGroups[ count ].push( i );
               }
            }
         }

      // matchingGroups is a map between the count number and the array of compatible groups
      // we select the groups with the highest matching count.
      // Note: Object.keys returns strings, so sort() is lexicographic. This is correct
      // under the assumption that keyword match counts never exceed 9 (realistically 3-4).
      let sortedCounts = Object.keys( matchingGroups );
      sortedCounts.sort();
      sortedCounts.reverse();

      // search for the best dark within the candidates
      let compatibleGroups = [];

      // extract the candidates
      if ( sortedCounts.length > 0 )
      {
         // keep only the highest matching if required
         if ( onlyHighestMatches )
            sortedCounts = [ sortedCounts[ 0 ] ];

         // internally sort groups by keyword precedence
         let kwNames = engine.keywords.names();
         sortedCounts.forEach( count =>
         {
            // get the groups with the current count value
            let currentGroups = matchingGroups[ count ].map( i => groups[ i ] );
            // sort by keyword precedence
            currentGroups.sort( ( a, b ) =>
            {
               // process keywords respecting the order, if a keyword is found in group A
               // but not in group B then A has precedence and the other way around. If they
               // have the same keywords then the behavior is undefined
               for ( let j = 0; j < kwNames.length; ++j )
               {
                  let aKeyword = a.keywords[ kwNames[ j ] ];
                  let bKeyword = b.keywords[ kwNames[ j ] ];
                  if ( aKeyword != undefined && bKeyword == undefined )
                     return -1;
                  if ( aKeyword == undefined && bKeyword != undefined )
                     return 1;
               }
               return 0;
            } );
            compatibleGroups = compatibleGroups.concat( currentGroups.map( g => (
            {
               group: g,
               count: count
            } ) ) );
         } );
      }

      return compatibleGroups;
   }

   // ........................................................................

   /**
    * Returns the list of groups that matches the criteria provided.
    * This function accepts an object with key - value that must be matched by the returned group.
    *
    * @param {{}} properties key-value pair to be matched
    * @returns {Array<FrameGroup>} array of groups matching all provided properties
    */
   getCalibrationGroupsMatching( properties )
   {
      let groups = this.engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      return groups.reduce( ( matchingGroups, group ) =>
      {
         let keys = Object.keys( properties );
         for ( let i = 0; i < keys.length; ++i )
         {
            let key = keys[ i ];
            // handle the special case of the 'size' property object
            if ( key == "size" )
            {
               if ( group[ key ] && ( group[ key ].width != properties[ key ].width || group[ key ].height != properties[ key ].height ) )
                  return matchingGroups;
            }
            else if ( group[ key ] != properties[ key ] )
               return matchingGroups;
         }
         matchingGroups.push( group );
         return matchingGroups;
      }, [] );
   }

   // ........................................................................

   /**
    * Searches for the Master Bias Group matching the given parameters.
    *
    * @param {Numeric} binning Binning value to match.
    * @param {Object} size An object with properties 'width' and 'height' representing the expected size.
    * @param {Boolean} isMaster True if the group must contain a master file; false otherwise.
    * @param {{String:String}} keywords The keywords key-value map.
    * @returns {Object|undefined} The matching master bias group on success, or undefined if no match is found.
    */
   getMasterBiasGroup( binning, size, isMaster, keywords )
   {
      let compatibleBias = this.getCompatibleCalibrationGroups( ImageType.Bias, size, keywords, true /* onlyHighestMatches */ );

      for ( let i = 0; i < compatibleBias.length; ++i )
         if ( !isMaster || compatibleBias[ i ].group.hasMaster )
            if ( compatibleBias[ i ].group.binning == binning )
               return compatibleBias[ i ].group;
      return undefined;
   }

   // ........................................................................

   /**
    * Returns the group containing or generating the best matching master dark given the parameters.
    *
    * @param {ImageType} imageType the image type for which we want the matching dark (flat or light frames)
    * @param {Numeric} binning binning to match
    * @param {Numeric} exposureTime exposure time to search for
    * @param {Object} size {width:Numeric, height:Numeric}
    * @param {Boolean} findExactExposureTime true if exposure time must match exactly, false otherwise
    * @param {{String: String}} keywords { key: value } keywords object
    * @param {Boolean} isMaster true if the group must already contain the master file
    * @param {Boolean} logResult true if the search result of the master dark needs to print some log
    *                      information on the console
    * @returns the matching master dark group
    */
   getMasterDarkGroup( imageType, binning, exposureTime, size, findExactExposureTime, keywords, isMaster, logResult )
   {
      // Assume no binning when binning is unknown.
      if ( binning <= 0 )
         binning = 1;

      // Ensure we get the most exposed master dark frame when the exposure time
      // is unknown. This favors scaling down dark current during optimization.
      let knownTime = exposureTime > 0;
      if ( !knownTime )
         exposureTime = 1.0e+10;

      // By default we do not search for exact duration darks.
      if ( findExactExposureTime === undefined )
         findExactExposureTime = false;

      // search for the best dark within the candidates
      let masterDarkGroup = undefined;
      let candidateDarks = this.getCompatibleCalibrationGroups( ImageType.Dark, size, keywords, imageType !== ImageType.Light /* onlyHighestMatches */ );

      let foundTime = 1.0e+20;
      let bestSoFar = 1.0e+20;
      let bestMatchingCount = -1;
      for ( let i = 0; i < candidateDarks.length; ++i )
         if ( !isMaster || candidateDarks[ i ].group.hasMaster )
            if ( candidateDarks[ i ].group.imageType == ImageType.Dark )
               if ( candidateDarks[ i ].group.binning == binning )
               {
                  let d = Math.abs( candidateDarks[ i ].group.exposureTime - exposureTime );
                  if ( d <= bestSoFar && ( !findExactExposureTime || ( findExactExposureTime && d < BPP.Constants.FLAT_DARK_TOLERANCE ) ) )
                  {
                     // if the best equals the current exposure then we keep it only if the new best has a higher number matching keywords
                     if ( d == bestSoFar )
                        if ( candidateDarks[ i ].count <= bestMatchingCount )
                           continue;

                     bestMatchingCount = candidateDarks[ i ].count;
                     masterDarkGroup = candidateDarks[ i ].group;
                     foundTime = candidateDarks[ i ].group.exposureTime;
                     bestSoFar = d;
                  }
               }

      if ( masterDarkGroup && logResult )
      {
         if ( foundTime > 0 )
         {
            if ( findExactExposureTime )
               console.noteln( "<end><cbr><br>* Searching for a master flat dark with exposure time = "
                  + exposureTime + "s -- found." );
            else if ( knownTime )
               console.noteln( "<end><cbr><br>* Searching for a master dark frame with exposure time = ",
                  exposureTime + "s -- best match is ", foundTime + "s" );
            else
               console.noteln( "<end><cbr><br>* Using master dark frame with exposure time = ",
                  foundTime + "s to calibrate unknown exposure time frame(s)." );
         }
         else
         {
            if ( findExactExposureTime )
               console.noteln( "<end><cbr><br>* Searching for a master flat dark with exposure time = ",
                  exposureTime + "s -- not found." );
            else if ( knownTime )
               console.noteln( "<end><cbr><br>* Searching for a master dark frame with exposure time = ",
                  exposureTime + "s -- best match is a master dark frame of unknown exposure time." );
            else
               console.noteln( "<end><cbr><br>* Master dark match with an unknown exposure time." );
         }
      }

      return masterDarkGroup;
   }

   // ........................................................................

   /**
    * Returns the group containing or generating the best matching master flat given the parameters.
    *
    * @param {Numeric} binning The binning value to match.
    * @param {Object} size An object with properties 'width' and 'height' representing the image size.
    * @param {String} filter The filter to match.
    * @param {Boolean} isCFA Indicates whether the image is a CFA (Color Filter Array) image.
    * @param {Boolean} isMaster True if the group must already contain the master file; false otherwise.
    * @param {{String:String}} keywords The keywords key-value map.
    * @returns {Object|undefined} The matching master flat group on success, or undefined if no match is found.
    */
   getMasterFlatGroup( binning, size, filter, isCFA, isMaster, keywords )
   {
      // search for the best flat group within the candidates
      let candidateFlats = this.getCompatibleCalibrationGroups( ImageType.Flat, size, keywords, false /* onlyHighestMatches */ );

      for ( let i = 0; i < candidateFlats.length; ++i )
         if ( !isMaster || candidateFlats[ i ].group.hasMaster )
            if ( candidateFlats[ i ].group.imageType == ImageType.Flat )
               if ( candidateFlats[ i ].group.binning == binning && candidateFlats[ i ].group.filter == filter && candidateFlats[ i ].group.isCFA == isCFA )
                  return candidateFlats[ i ].group;
      return undefined;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-CalibrationMatcher.js - Released 2026-05-10T11:05:00Z
