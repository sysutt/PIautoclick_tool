// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Operations.js - Released 2026-05-10T11:05:00Z
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
 * Base class for all batch preprocessing operations.
 * Provides common functionality and structure for preprocessing steps.
 *
 * @param {String} name - Operation name displayed in UI
 * @param {Object} group - Frame group this operation works on
 * @param {Boolean} trackable - Whether operation progress can be tracked
 */
var BPPOperationBlock = class extends OperationBlock
{
   constructor( name, group, trackable )
   {
      super();

      this.name = name;
   this.group = group;
   this.trackable = trackable;
   this.hasWarnings = false;
   this.statusMessage = "";

   // only trackable WBPP operations trigger the pipeline event script
   this.triggersEventScript = trackable;

   // operation execution time (in seconds)
   this.executionTime = 0;
   // average time per frame
   this.averageExecution = 0;

   this.run = ( environment, requestInterruption ) =>
   {
      return this._run( environment, requestInterruption );
   };

   this.updateGroupDescription = ( withActiveFrames, reportFileItems ) =>
   {
      this.groupDescription = ( group ? group.toShortString( withActiveFrames, reportFileItems ) : "" );
   };

   this.spaceRequired = () =>
   {
      return 0;
   };

      this.updateGroupDescription();
   }
}

/**
 * Calibration operation that applies bias, dark and flat corrections to raw frames.
 * Handles both fast integration frames and regular frames separately.
 * Manages calibration file caching and tracks success/failure of calibration per frame.
 */
StackEngine.prototype.calibrationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Calibration", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      return frameGroup.groupSize();
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Calibration",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = () =>
   {
      let groupType = StackEngine.imageTypeToString( frameGroup.imageType )

      // calibrate in two steps, first the frames that will be integrated with fast integration
      // and next the others
      let fastIntegrationFrames = [];
      let regularIntegrationFrames = [];
      {
         let activeFrames = frameGroup.activeFrames();
         if ( frameGroup.imageType == ImageType.Light )
         {
            for ( let i = 0; i < activeFrames.length; ++i )
            {
               if ( activeFrames[ i ].__fastIntegration )
                  fastIntegrationFrames.push( activeFrames[ i ] );
               else
                  regularIntegrationFrames.push( activeFrames[ i ] );
            }
         }
         else
            regularIntegrationFrames = activeFrames;
      }

      // prepare the two dataset to calibrate
      let originalItems = frameGroup.fileItems;
      let calibrationDataSet = [
      {
         fileItems: fastIntegrationFrames.map( item => item.fileItem ),
         doMeasurements: false
      },
      {
         fileItems: regularIntegrationFrames.map( item => item.fileItem ),
         doMeasurements: undefined
      } ];

      let nCached = 0;
      let nGenerated = 0;
      let nFailed = 0;

      for ( let c = 0; c < calibrationDataSet.length; ++c )
      {
         frameGroup.fileItems = calibrationDataSet[ c ].fileItems;
         let activeFrames = frameGroup.activeFrames();
         if ( activeFrames.length == 0 )
            continue;

         // calibrate the remaining frames
         let
         {
            calibratedFiles,
            nCached: _nCached,
            nGenerated: _nGenerated
         } = engine.imageProcessor.doCalibrate( frameGroup, calibrationDataSet[ c ].doMeasurements );
         if ( !calibratedFiles )
         {
            // calibration skipped
            frameGroup.fileItems = originalItems;
            return OperationBlockStatus.CANCELED;
         }
         else
         {
            // check which active frame has been successfully processed
            for ( let c = 0; c < activeFrames.length; ++c )
            {
               let inputFile = activeFrames[ c ].current
               let outputFile = calibratedFiles[ c ];

               if ( outputFile != undefined && outputFile.length > 0 )
               {
                  if ( File.exists( outputFile ) )
                  {
                     activeFrames[ c ].processingSucceeded( BPP.FrameProcessingStep.CALIBRATION, outputFile );
                     console.writeln( "Calibration frame " + c + ": <raw>" + inputFile + "</raw> ---> <raw>" + outputFile + "</raw>" );
                  }
                  else
                  {
                     // non-existing file can occur only with processed files
                     nFailed++;
                     _nGenerated--;
                     console.warningln( "** Warning: Calibration frame " + c + ": <raw>" + outputFile + "</raw> ---> [ FAILED: Calibrated file not found ]" );
                     engine.processLogger.addWarning( "File does not exist after image calibration: " + outputFile );
                     activeFrames[ c ].processingFailed();
                  }
               }
               else
               {
                  console.warningln( "** Warning: Calibration frame " + c + ": <raw>" + inputFile + "</raw> ---> [ FAILED ]" );
                  engine.processLogger.addWarning( "Calibration failed for image: " + inputFile );
                  activeFrames[ c ].processingFailed();
                  _nGenerated--;
                  nFailed++;
               }
            }
         }

         nGenerated += _nGenerated;
         nCached += _nCached;
      }
      // report how many frames exist after calibration
      frameGroup.fileItems = originalItems;
      let calibratedActiveFrames = frameGroup.activeFrames();
      if ( calibratedActiveFrames.length < 1 )
      {
         console.warningln( "** Warning: No " + groupType + " frames found after calibration." );
         engine.processLogger.addError( "No " + groupType + " frames found after calibration." );
         this.statusMessage = "no frames found after calibration";
         return OperationBlockStatus.FAILED;
      }

      engine.processLogger.addSuccess( "Calibration completed", calibratedActiveFrames.length + " " + groupType + " frame" + ( calibratedActiveFrames.length == 1 ? "" : "s" ) + " calibrated." );
      this.statusMessage = WBPPUtils.resultCountToString( nCached, nGenerated, nFailed, "calibrated" );
      this.hasWarnings = nFailed > 0;
      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Linear Pattern Subtraction operation to correct linear defects in light frames.
 * Applies LPS correction to preprocessed groups based on binning.
 * Handles caching of corrected frames and tracks success/failure.
 */
StackEngine.prototype.LPSOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Linear Defects Correction ", undefined, true /* trackable */ );

   this.spaceRequired = () =>
   {
      let preprocessGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      let size = 0;
      let bins = preprocessGroups.reduce( ( acc, group ) =>
      {
         acc[ group.binning ] = true;
         return acc
      },
      {} );

      Object.keys( bins ).forEach( bin =>
      {
         let firstFound = false;
         for ( let i = 0; i < preprocessGroups.length; ++i )
            if ( preprocessGroups[ i ].binning == bin && !preprocessGroups[ i ].isCFA )
            {
               size += preprocessGroups[ i ].groupSize();
               if ( !firstFound )
               {
                  // include the master generated for LPS execution
                  firstFound = true;
                  size += preprocessGroups[ i ].frameSize();
               }
            }
      } );

      return size;
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "LPS",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function()
   {
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Apply linear defects correction to light frames" );
      console.noteln( BPP.Format.SEPARATOR );

      let groupsPRE = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      let
      {
         nCached,
         nGenerated,
         nFailed
      } = engine.imageProcessor.doLinearPatternSubtraction( groupsPRE );

      let resultString = WBPPUtils.resultCountToString( nCached, nGenerated, nFailed, "corrected" );
      this.statusMessage = ( nCached + nGenerated + nFailed ) + " frame(s)" + ( resultString.length > 0 ? ", " + resultString : "" );
      this.hasWarnings = nFailed > 0;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End of linear defects correction process" );
      console.noteln( BPP.Format.SEPARATOR );

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Cosmetic Correction operation to fix hot/cold pixels and other artifacts.
 * Applies specified cosmetic correction template to frames.
 * Manages caching of corrected frames and handles both CFA and non-CFA data.
 */
StackEngine.prototype.CosmeticCorrectionOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Cosmetic Correction", frameGroup, true /* trackable */ );
   this.spaceRequired = () =>
   {
      return frameGroup.groupSize();
   }
   this.envForScript = () => (
   {
      name: "Cosmetic Correction",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      let cosmeticCorrectionTemplateId = frameGroup.ccData.CCTemplate;
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin cosmetic correction of light frames" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();
      let activeFrames = frameGroup.activeFrames();
      let filePaths = [];
      let nCached = 0;
      let nGenerated = 0;
      let nFailed = 0;
      let CC = ProcessInstance.fromIcon( cosmeticCorrectionTemplateId );
      if ( CC == null )
      {
         console.warningln( "** Warning: No such process icon: " + cosmeticCorrectionTemplateId + "; cosmetic correction will be skipped." );
         engine.processLogger.addWarning( "No such process icon: " + cosmeticCorrectionTemplateId + "; cosmetic correction will be skipped." );
         this.statusMessage = "process icon not found";
         return OperationBlockStatus.CANCELED;
      }
      else if ( !( CC instanceof CosmeticCorrection ) )
      {
         console.warningln( "** Warning: The specified icon does not transport an instance "
            + "of CosmeticCorrection: " + cosmeticCorrectionTemplateId + "; cosmetic correction will be skipped." );
         engine.processLogger.addWarning( "The specified icon does not transport an instance "
            + "of CosmeticCorrection: " + cosmeticCorrectionTemplateId + "; cosmetic correction will be skipped." );
         this.statusMessage = "wrong process icon found";
         return OperationBlockStatus.CANCELED;
      }
      else if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: no active frames." );
         engine.processLogger.addWarning( "No active frames." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }
      else
      {
         console.noteln( "Cosmetic Correction: applying " + cosmeticCorrectionTemplateId + " process icon." );
         engine.processLogger.addMessage( "Running <b>" + cosmeticCorrectionTemplateId + "</b> Cosmetic Correction process icon." );
         let subfolder = frameGroup.folderName();
         let cosmetizedDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/cosmetized/" + subfolder );
         filePaths = activeFrames.map( activeFrame => activeFrame.current );
         CC.outputDir = cosmetizedDirectory;
         CC.outputExtension = ".xisf";
         CC.prefix = "";
         CC.postfix = "_cc";
         CC.overwrite = true;
         CC.cfa = frameGroup.isCFA;
         let CCSource = CC.toSource( "JavaScript", "CC" /*varId*/ , 0 /*indent*/ ,
            SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
         console.writeln( BPP.Format.SEPARATOR2 );
         console.writeln( CCSource );
         console.writeln( BPP.Format.SEPARATOR2 );
         /**
          * Skip CC for files that have valid cached data. Cache is a map between an input file and an
          * output file:
          * [inputFile]: outputFile
          */
         let filesToProcess = filePaths;
         let cachedCount = 0;
         let cached = {};
         let CCCache = {};
         let CCcacheKey = engine.executionCache.keyFor( CCSource );
         if ( engine.executionCache.hasCacheForKey( CCcacheKey ) )
         {
            console.noteln( "Cosmetic correction has cached data for key ", CCcacheKey );
            if ( ( !CC.useMasterDark || ( CC.useMasterDark && engine.executionCache.isFileUnmodified( CCcacheKey, CC.masterDarkPath ) ) ) )
            {
               // Cosmetic Correction has already been executed with such configuration and the (eventually used) master
               // dark is unchanged.
               // We avoid to correct frames that have already been processed by this configuration.
               filesToProcess = [];
               CCCache = engine.executionCache.cacheForKey( CCcacheKey );
               for ( let i = 0; i < filePaths.length; ++i )
               {
                  let inputFile = filePaths[ i ];
                  let outputFile = CCCache[ inputFile ];
                  if ( outputFile != undefined
                     && engine.executionCache.isFileUnmodified( CCcacheKey, inputFile )
                     && engine.executionCache.isFileUnmodified( CCcacheKey, outputFile )
                  )
                  {
                     console.noteln( "Cosmetic Correction: cache ", inputFile, " --> ", outputFile );
                     cached[ inputFile ] = outputFile;
                     cachedCount++;
                  }
                  else
                  {
                     console.noteln( "Cosmetic Correction: process ", inputFile );
                     filesToProcess.push( inputFile );
                  }
               }
            }
         }
         else
         {
            console.noteln( "Cosmetic correction has no cached data for key ", CCcacheKey );
         }
         // in process container we store the full CC files
         CC.targetFrames = WBPPUtils.enableTargetFrames( filePaths, 2 );
         engine.processContainer.add( CC );
         engine.pipelineManager.flushProcessContainer();
         if ( filesToProcess.length > 0 )
         {
            CC.targetFrames = WBPPUtils.enableTargetFrames( filesToProcess, 2 );
            CC.executeGlobal();
         }
         else if ( cachedCount > 0 )
            console.noteln( "Cosmetic Correction: all ", filePaths.length, " files are cached, execution is skipped." )
         /*
          * ### FIXME: CosmeticCorrection should provide read-only output
          * data, including the full file path of each output image.
          */
         for ( let c = 0; c < filePaths.length; ++c )
         {
            let filePath = filePaths[ c ];
            let ccFilePath = cosmetizedDirectory + '/' + File.extractName( filePath ) + "_cc" + ".xisf";
            if ( cached[ filePath ] )
            {
               activeFrames[ c ].processingSucceeded( BPP.FrameProcessingStep.CC, ccFilePath );
               nCached++;
            }
            else
            {
               // we mark as successful the frames that succeeded but we don't mark as failed frames for which CC failed such that wa can continue
               // using the uncosmetized versions
               if ( File.exists( ccFilePath ) )
               {
                  activeFrames[ c ].processingSucceeded( BPP.FrameProcessingStep.CC, ccFilePath );
                  // cache the result
                  CCCache[ filePath ] = ccFilePath;
                  engine.executionCache.cacheFileLMD( CCcacheKey, filePath );
                  engine.executionCache.cacheFileLMD( CCcacheKey, ccFilePath );
                  nGenerated++;
               }
               else
               {
                  console.warningln( "** Warning: File does not exist after cosmetic correction: <raw>" + ccFilePath + "</raw>, the uncosmetized frame <raw>" + activeFrames[ c ].current + "</raw> will be used." );
                  engine.processLogger.addWarning( "File does not exist after cosmetic correction: " + ccFilePath + ", the uncosmetized frame " + activeFrames[ c ].current + " will be used." );
                  nFailed++;
               }
            }
         }
         if ( nFailed == activeFrames.length )
         {
            console.warningln( "** Warning: All cosmetic corrected light frame files have been removed or cannot be accessed. Uncosmetized frames will be used." );
            engine.processLogger.addWarning( "All cosmetic corrected light frame files have been removed or cannot be accessed. Uncosmetized frames will be used." );
            this.statusMessage = "no corrected frames found";
            this.hasWarnings = true;
         }
         else if ( nFailed == 0 )
         {
            engine.processLogger.addSuccess( "Cosmetic correction completed", activeFrames.length + " light frame" + ( activeFrames.length > 1 ? "s have" : "has" ) + " been calibrated." );
         }
         else
         {
            let successCount = activeFrames.length - nFailed;
            engine.processLogger.addSuccess( "Cosmetic correction completed", successCount + " light frame" + ( successCount > 1 ? "s have" : "has" ) + " been cosmetized." );
            this.statusMessage = nFailed + " frame" + ( nFailed > 1 ? "s" : "" ) + " failed";
            this.hasWarnings = true;
         }
         // update the cache
         engine.executionCache.setCache( CCcacheKey, CCCache );
         if ( CC.useMasterDark )
            engine.executionCache.cacheFileLMD( CCcacheKey, CC.masterDarkPath );
         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* End cosmetic correction of light frames" );
         console.noteln( BPP.Format.SEPARATOR );
      }
      this.statusMessage = WBPPUtils.resultCountToString( nCached, nGenerated, nFailed, "corrected" );
      this.hasWarnings = this.hasWarnings || nFailed > 0;
      // return the proper status
      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Debayer operation to convert CFA (Color Filter Array) data to RGB.
 * Supports different debayer methods and output modes (combined/separated channels).
 * Handles caching and tracks success/failure per frame.
 */
StackEngine.prototype.DebayerOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Debayer", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      let groupsize = frameGroup.groupSize();
      let size = 0;
      switch ( engine.debayerOutputMethod )
      {
         case BPP.DebayerOutputMode.COMBINED:
            size = groupsize * 3; // from mono to RGB
            break;
         case BPP.DebayerOutputMode.BOTH:
            size = groupsize * 6; // consider the combined RGB output (3x) + 3 mono channels
            break;
         case BPP.DebayerOutputMode.SEPARATED:
            if ( engine.debayerActiveChannelR )
               size += groupsize; // R only is Gray
            if ( engine.debayerActiveChannelG )
               size += groupsize; // G only is Gray
            if ( engine.debayerActiveChannelB )
               size += groupsize; // B only is Gray
      }

      return size;
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Debayer",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      let failed = false;

      if ( frameGroup.isCFA )
      {

         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* Begin demosaicing of light frames" );
         console.noteln( BPP.Format.SEPARATOR );

         let activeFrames = frameGroup.activeFrames();
         let nCached = 0;
         let nGenerated = 0;
         let nFailed = 0;

         if ( activeFrames.length == 0 )
         {
            // report the issue
            console.warningln( "** Warning: No active light frames in the group." );
            engine.processLogger.addError( "No active light frames in the group." );
            this.statusMessage = "no active frames";
            return OperationBlockStatus.CANCELED;
         }
         else
         {

            engine.processLogger.addSuccess( "Demosaicing with pattern", frameGroup.CFAPatternString() );
            frameGroup.log();
            console.writeln( "CFA pattern: ", frameGroup.CFAPatternString() );
            console.writeln( "Demosaicing method: ", frameGroup.debayerMethodString() );

            let DB = new Debayer;

            let subfolder = frameGroup.folderName();
            let debayerDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/debayered/" + subfolder );

            // we separate the active frames in two groups. one contains frames that are integrated with fast integration,
            // the other contains the remaining frames in the group.
            let fastIntegrationFrames = [];
            let regularFrames = [];
            for ( let i = 0; i < activeFrames.length; ++i )
               if ( activeFrames[ i ].__fastIntegration )
                  fastIntegrationFrames.push( activeFrames[ i ] );
               else
                  regularFrames.push( activeFrames[ i ] );
            let debayreData = [
            {
               frames: fastIntegrationFrames,
               doMeasure: false
            },
            {
               frames: regularFrames,
               doMeasure: engine.subframeWeightingEnabled
            } ];

            let channels = [];

            for ( let dd = 0; dd < debayreData.length; ++dd )
            {

               let localActiveFrames = debayreData[ dd ].frames;
               if ( localActiveFrames.length == 0 )
                  continue;

               let filePaths = localActiveFrames.map( activeFrame => activeFrame.current );
               DB.inputHints = engine.imageProcessor.inputHints();
               DB.cfaPattern = frameGroup.CFAPattern;
               DB.debayerMethod = frameGroup.debayerMethod;
               // N.B. For CFAs, evaluate noise and signal with Debayer instead of ImageCalibration
               DB.evaluateNoise = DB.evaluateSignal = !engine.fastMode && debayreData[ dd ].doMeasure;
               DB.outputDirectory = debayerDirectory;
               DB.outputExtension = ".xisf";
               DB.outputPostfix = "_d";
               DB.overwriteExistingFiles = false;

               /**
                * Check if some files are already cached and can be skipped
                */
               let DBSource = DB.toSource( "JavaScript", "DB" /*varId*/ , 0 /*indent*/ ,
                  SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();

               // we set the output configuration after creating the caching keys to share the cached files amongst all configurations
               DB.outputRGBImages = engine.debayerOutputMethod != BPP.DebayerOutputMode.SEPARATED;
               DB.outputSeparateChannels = engine.debayerOutputMethod != BPP.DebayerOutputMode.COMBINED;

               // define the channels involved
               switch ( engine.debayerOutputMethod )
               {
                  case BPP.DebayerOutputMode.COMBINED:
                     channels = [ "" ];
                     break;
                  case BPP.DebayerOutputMode.SEPARATED:
                     channels = [ BPP.AssociatedChannel.R, BPP.AssociatedChannel.G, BPP.AssociatedChannel.B ];
                     break;
                  default:
                     channels = [ "", BPP.AssociatedChannel.R, BPP.AssociatedChannel.G, BPP.AssociatedChannel.B ];
               }

               let filesToDebayer = filePaths;
               let cachedCount = 0;
               let cached = {};
               let DBCache = {};
               let DBcacheKey = engine.executionCache.keyFor( DBSource );
               if ( engine.executionCache.hasCacheForKey( DBcacheKey ) )
               {
                  console.noteln( "Debayer has cached data for key ", DBcacheKey );

                  // The cache is a map with the input file and the array of output files previously generated
                  DBCache = engine.executionCache.cacheForKey( DBcacheKey );
                  filesToDebayer = [];

                  for ( let i = 0; i < filePaths.length; ++i )
                  {
                     let inputFile = filePaths[ i ];
                     let outputFiles = DBCache[ inputFile ];

                     // output files is always an array of 4 file paths, RGB, R, G and B channels.
                     // depending on the debayer output mode, only the proper output files are checked

                     if ( outputFiles == undefined )
                        // we don't have any cached result for this input file
                        filesToDebayer.push( inputFile );
                     else
                     {
                        // the original file must be unchanged
                        let useCache = engine.executionCache.isFileUnmodified( DBcacheKey, inputFile );

                        // all output channel files must be unchanged
                        for ( let j = 0;
                           ( j < channels.length ) && useCache; ++j )
                        {
                           let channel = channels[ j ];
                           let outputFile = outputFiles[ channel ];
                           useCache = engine.executionCache.isFileUnmodified( DBcacheKey, outputFile );
                        }

                        if ( useCache )
                        {
                           cached[ inputFile ] = outputFiles;
                           cachedCount++;
                           console.noteln( "Debayer will use cache for file: ", inputFile );
                        }
                        else
                        {
                           filesToDebayer.push( inputFile );
                           console.noteln( "Debayer will demosaic: ", inputFile );
                        }
                     }
                  }
               }
               else
               {
                  console.noteln( "Debayer has no cached data for key ", DBcacheKey );
               }

               // process is saved in container with the full list of files to be debayered
               {
                  DB.targetItems = WBPPUtils.enableTargetFrames( filePaths, 2 );

                  let DBSource = DB.toSource( "JavaScript", "DB" /*varId*/ , 0 /*indent*/ ,
                     SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();

                  console.writeln( BPP.Format.SEPARATOR2 );
                  console.writeln( DBSource );
                  console.writeln( BPP.Format.SEPARATOR2 );
                  engine.processContainer.add( DB );
                  engine.pipelineManager.flushProcessContainer();
               }

               let debayeredFiles = [];
               let success = true;
               if ( filesToDebayer.length > 0 )
               {
                  DB.targetItems = WBPPUtils.enableTargetFrames( filesToDebayer, 2 );
                  success = DB.executeGlobal();
               }
               else
                  console.noteln( "Debayer has no files to process" );

               // track which output files are referenced by the cache
               let cachedInputFiles = {};

               let j = 0;
               filePaths.forEach( filePath =>
               {
                  let fileMap = {};

                  if ( cached[ filePath ] != undefined )
                  {
                     let cachedData = cached[ filePath ];
                     for ( let k = 0; k < channels.length; ++k )
                     {
                        let channel = channels[ k ];
                        fileMap[ channel ] = cachedData[ channel ];
                     }
                     cachedInputFiles[ filePath ] = true;
                  }
                  else
                  {
                     let outputRow = DB.outputFileData[ j++ ];
                     let lastIndx = outputRow.length - 1;
                     let DBoutputMap = {};
                     DBoutputMap[ "" ] = outputRow[ 0 ];
                     DBoutputMap[ BPP.AssociatedChannel.R ] = outputRow[ lastIndx - 2 ];
                     DBoutputMap[ BPP.AssociatedChannel.G ] = outputRow[ lastIndx - 1 ];
                     DBoutputMap[ BPP.AssociatedChannel.B ] = outputRow[ lastIndx ];

                     // update the cached data of the only the relevant channels
                     for ( let k = 0; k < channels.length; ++k )
                     {
                        let channel = channels[ k ];
                        fileMap[ channel ] = DBoutputMap[ channel ];
                     }
                     cachedInputFiles[ filePath ] = false;
                  }

                  debayeredFiles.push( fileMap );
               } );

               if ( ( !success || debayeredFiles.length == 0 ) && cachedCount == 0 )
               {
                  // mark all active frames as failed
                  localActiveFrames.forEach( activeFrame => activeFrame.processingFailed() );
                  // report the issue
                  console.warningln( "** Warning: Light frames demosaicing failed." );
                  engine.processLogger.addError( "Light frames demosaicing failed." );
                  nFailed += localActiveFrames.length;
               }
               else
               {
                  // check which acive frame has been successfully processed
                  for ( let c = 0; c < localActiveFrames.length; ++c )
                  {
                     let inputFilePath = localActiveFrames[ c ].current;
                     let currentBaseName = File.extractName( inputFilePath );
                     let outputFiles = debayeredFiles[ c ];
                     let isCached = cachedInputFiles[ inputFilePath ];

                     // process the results for each active channel
                     let frameFailed = false;
                     channels.forEach( channel =>
                     {

                        let outputFilePath = outputFiles[ channel ];

                        if ( outputFilePath != undefined && outputFilePath.length > 0 )
                        {
                           if ( File.exists( outputFilePath ) )
                           {
                              localActiveFrames[ c ].processingSucceeded( BPP.FrameProcessingStep.DEBAYER, outputFilePath, channel );
                              engine.executionCache.cacheFileLMD( DBcacheKey, inputFilePath );
                              engine.executionCache.cacheFileLMD( DBcacheKey, outputFilePath );
                              outputFiles[ channel ] = outputFilePath;
                           }
                           else
                           {
                              let channelName = channel.length > 0 ? " channel " + channel : "";
                              console.warningln( "** Warning: File does not exist after image demosaicing" + channelName + ": <raw>" + currentBaseName + "</raw>" );
                              engine.processLogger.addWarning( "File does not exist after image demosaicing " + channelName + ": " + currentBaseName );
                              localActiveFrames[ c ].processingFailed( channel );
                              frameFailed = true;
                              // invalidate the cache and the LMD for that file
                              outputFiles[ channel ] = undefined;
                              engine.executionCache.invalidateFileLMD( DBcacheKey, inputFilePath );
                              engine.executionCache.invalidateFileLMD( DBcacheKey, outputFilePath );
                           }
                        }
                        else
                        {
                           let channelName = channel.length > 0 ? "channel " + channel + " of " : "";
                           console.warningln( "** Warning: Debayer failed for " + channelName + "frame: <raw>" + currentBaseName + "</raw>" );
                           engine.processLogger.addWarning( "Debayer failed for " + channelName + "frame: " + currentBaseName );
                           localActiveFrames[ c ].processingFailed( channel );
                           frameFailed = true;
                           // invalidate the cache and  the LMD for that file
                           outputFiles[ channel ] = undefined;
                           engine.executionCache.invalidateFileLMD( DBcacheKey, inputFilePath );
                           engine.executionCache.invalidateFileLMD( DBcacheKey, outputFilePath );
                        }
                     } );

                     if ( frameFailed )
                        nFailed++;
                     else if ( isCached )
                        nCached++;
                     else
                        nGenerated++;

                     // update the list of output files for the given input file
                     DBCache[ inputFilePath ] = outputFiles;
                  }
                  // save the DB cache
                  engine.executionCache.setCache( DBcacheKey, DBCache );
               }
            }

            // report the status of the channels
            let emptyChannels = [];
            channels.forEach( channel =>
            {
               let debayerChannelName;
               switch ( channel )
               {
                  case "":
                     debayerChannelName = "combined";
                     break;
                  case BPP.AssociatedChannel.R:
                     debayerChannelName = "separated red";
                     break;
                  case BPP.AssociatedChannel.G:
                     debayerChannelName = "separated green";
                     break;
                  case BPP.AssociatedChannel.B:
                     debayerChannelName = "separated blue";
               }

               let debayeredActiveFrames = frameGroup.activeFrames( channel );
               if ( debayeredActiveFrames.length < 1 )
               {
                  let msg = "** Warning: No frames found for " + debayerChannelName + " channel after demosaicing.";
                  console.warningln( msg );
                  engine.processLogger.addError( msg );
                  emptyChannels.push( debayerChannelName );
               }
               else
               {
                  engine.processLogger.addSuccess( "Demosaicing completed", debayeredActiveFrames.length + " light frame" + ( debayeredActiveFrames.length == 1 ? "" : "s" ) + "  demosaiced for " + debayerChannelName + " channel." );
               }
            } )

            if ( emptyChannels.length > 0 )
            {
               let last = emptyChannels.pop();
               let commaSeparatedList = emptyChannels.join( ", " ) + ( emptyChannels.length > 0 ? " and " : "" ) + last;
               this.statusMessage += "\nno frames generated for " + commaSeparatedList + " channel";
            }

            // set the status message
            this.statusMessage = WBPPUtils.resultCountToString( nCached, nGenerated, nFailed, "demosaiced" );
            this.hasWarnings = nFailed > 0;
         }

         failed = nFailed == activeFrames.length;

         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* End demosaicing of light frames" );
         console.noteln( BPP.Format.SEPARATOR );
      }




      if ( failed )
      {
         this.statusMessage = "demosaicing failed";
         return OperationBlockStatus.FAILED;
      }
      else
         return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to prepare reference frame data for registration.
 * Analyzes groups and determines appropriate reference frames.
 * Supports manual selection, auto single, and keyword-based reference selection.
 */
StackEngine.prototype.ReferenceFrameDataPreparationOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Reference frame data preparation", undefined, false /* trackable */ );

   /**
    * data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Reference frame data preparation",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function( environment, requestInterruption )
   {
      // here we continue using the post-process groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );

      // remove non-active groups
      groups = groups.filter( g => g.isActive );

      // returns immediatly if no post-process groups are given (this could be the case when WBPP is used to generate the master
      // bias / dark / flat only).
      if ( groups.length == 0 )
      {
         // no POST calibration groups, we can interrupt the whole processing
         requestInterruption();
         return OperationBlockStatus.CANCELED;
      }

      // ----------------------------------------------------------------------------
      // MEASURING FRAMES
      // ----------------------------------------------------------------------------

      // List of cases which requires to measure the images:
      // 1. if I choose to generate the weights
      // 2. if I do the registration and I want the best reference image to be auto-selcted
      // 3. local normalization is enabled
      //
      // referenceFrameData structure:
      // {
      //    [key]: {
      //       groups: Array<FrameGroup>,  // frame groups associated with this key
      //       referenceImage: String,     // only for MANUAL mode - the selected reference path
      //       lowestBinning: Number       // minimum binning among groups (added after construction)
      //    }
      // }
      //
      // Keys depend on engine.bestFrameReferenceMethod:
      //   - MANUAL:      "__manual__"   -> { groups: [], referenceImage: <path> }
      //   - AUTO_SINGLE: "__single__"   -> { groups: [all active POST groups] }
      //   - KEYWORD:     <keyword_value> or "__undefined__" -> { groups: [matching groups] }
      //
      // Used by MeasurementOperation and ReferenceFrameSelectionOperation.
      // Stored in environment.referenceFrameData for inter-operation communication.
      let referenceFrameData = {};

      // assign the manual reference frame
      if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL )
      {
         // assume that the file is not added to the session
         let currentReferenceImage = engine.referenceImage;
         // check if the reference frame is one frame in the session
         let referenceFrameFileItem = engine.groupsManager.getReferenceFrameFileItem( engine.referenceImage );
         if ( referenceFrameFileItem )
         {
            // precedence is given to the green channel if separate debayer channels has been generated for the reference frame
            if ( referenceFrameFileItem.current[ BPP.AssociatedChannel.G ] )
            {
               currentReferenceImage = referenceFrameFileItem.current[ BPP.AssociatedChannel.G ]
               referenceFrameFileItem.markAsReference( BPP.AssociatedChannel.G );
            }
            else if ( referenceFrameFileItem.current[ "default" ] )
            {
               currentReferenceImage = referenceFrameFileItem.current[ "default" ]
               referenceFrameFileItem.markAsReference( "default" );
            }
            else
            {
               currentReferenceImage = referenceFrameFileItem.filePath;
            }
         }
         // by convention assume to configure the "auto_single" mode with the manual reference file
         referenceFrameData[ "__manual__" ] = {
            /* no groups to be measured */
            groups: [],
            referenceImage: currentReferenceImage
         }
      }
      else if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.AUTO_SINGLE )
      {
         referenceFrameData[ "__single__" ] = {
            /* measure all groups  */
            groups: groups
         }
      }
      else
      {
         // aggregate groups by keyword
         referenceFrameData = groups.reduce( ( acc, group ) =>
         {
            let value = group.keywords[ engine.bestFrameReferenceKeyword ] || "__undefined__";
            if ( acc[ value ] )
               acc[ value ].groups.push( group );
            else
               acc[ value ] = {
                  groups: [ group ]
               };
            return acc;
         },
         {} );
      }

      // for each keyword store the lowest binning
      Object.keys( referenceFrameData ).forEach( key =>
      {
         let groups = referenceFrameData[ key ].groups;
         let lowestBinning = groups.reduce( ( acc, group ) =>
         {
            return Math.min( group.binning, acc );
         }, 256 );
         referenceFrameData[ key ].lowestBinning = lowestBinning;
      } );

      // store the reference frame data for further processing
      environment.referenceFrameData = referenceFrameData;
      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to measure image quality metrics for frame evaluation.
 * Computes descriptors like FWHM, eccentricity, SNR etc.
 * Used for reference frame selection and weighting.
 */
StackEngine.prototype.MeasurementOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Measurements", undefined, true /* trackable */ );

   /**
    * data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Measurements",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function( environment )
   {
      let failed = false;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Perform image measurements" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();
      engine.processLogger.newLine();
      engine.processLogger.addMessage( "<b>*****************</b> <i>IMAGE MEASUREMENTS</i> <b>**************</b>" );

      // get the reference frame data from the environment
      // (see ReferenceFrameDataPreparationOperation for structure)
      let referenceFrameData = environment.referenceFrameData;

      // using the active post-process groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive );

      // retrieve the whole list of frames to be measured
      let framesToMeasure = [];

      // check if subframes weights are to be generated
      let generateSubframesWeights = engine.subframeWeightingEnabled && ( engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.FORMULA );
      let needsMeasurements = generateSubframesWeights || engine.localNormalization || engine.frameSelectionEnabled;
      let isWBPP = !engine.fastMode;
      // here we determine if we need to measure the frames in WBPP
      if ( isWBPP && needsMeasurements )
      {
         for ( let i = 0; i < groups.length; ++i )
         {
            let activeFrames = groups[ i ].activeFrames();
            // we measure only the first 5 frames in a fast integration group, unless frame selection is enabled
            if ( groups[ i ].fastIntegrationData.enabled && !engine.frameSelectionEnabled )
               activeFrames = activeFrames.slice( 0, 5 );
            framesToMeasure = framesToMeasure.concat( activeFrames );
         }
      }
      else
      {
         // measurement is used only to find the reference frame
         // measure only the groups with the lowest binning for each keyword
         framesToMeasure = Object.keys( referenceFrameData ).reduce( ( acc, key ) =>
         {
            let lowBinningGroups = referenceFrameData[ key ].groups.filter( group => group.binning == referenceFrameData[ key ].lowestBinning );
            return acc.concat( lowBinningGroups );
         }, [] ).reduce( ( acc, group ) =>
         {
            let activeFrames = group.activeFrames();
            // we measure only the first 5 frames in a fast integration group
            if ( group.fastIntegrationData.enabled )
               activeFrames = activeFrames.slice( 0, 5 );
            return acc.concat( activeFrames );
         }, [] );
      }

      if ( framesToMeasure.length == 0 )
      {
         console.writeln( "************************************************" );
         console.writeln( "subframeWeightingEnabled: ", engine.subframeWeightingEnabled );
         console.writeln( "localNormalization: ", engine.localNormalization );
         console.writeln( "frameSelectionEnabled: ", engine.frameSelectionEnabled );
         console.writeln( "needsMeasurements: ", needsMeasurements );
         console.writeln( "isWBPP: ", isWBPP );
         console.writeln( "framesToMeasure: ", framesToMeasure );
         console.criticalln( "*** Error: No frames to be measured." );
         engine.processLogger.addError( "No frames to be measured." );
         this.statusMessage = "No frames to be measured";
         this.hasWarnings = true;
         return OperationBlockStatus.CANCELED;
      }

      // measure the frames
      let
      {
         nCached,
         nMeasured,
         nFailed
      } = engine.subframeAnalyzer.computeDescriptors( framesToMeasure );

      console.noteln( "SS nCached   : ", nCached );
      console.noteln( "SS nMeasured : ", nMeasured );
      console.noteln( "SS nFailed   : ", nFailed );

      // report
      if ( ( nMeasured + nCached ) == framesToMeasure.length )
      {
         console.noteln( "All frame measurements completed successfully" );
         engine.processLogger.addSuccess( "Frames measurement", "completed successfully" );
      }
      else if ( nFailed < framesToMeasure.length )
      {
         let measuredCount = nMeasured + nCached;
         console.warningln( "** Warning: Measurements completed successfully for " + measuredCount + " light frame" + ( measuredCount == 1 ? "" : "s" ) + " over " + framesToMeasure.length + "." );
         engine.processLogger.addSuccess( "Measurements completed successfully", measuredCount + " light frame" + ( measuredCount == 1 ? "" : "s" ) + " over " + framesToMeasure.length + "." );
         this.statusMessage = "measurement failed on " + nFailed + " frame" + ( nFailed > 1 ? "s" : "" );
         this.hasWarnings = true;
      }
      else
      {
         console.criticalln( "*** Error: Frame measurement failed for all light frames." );
         engine.processLogger.addError( "Frame measurement failed for all light frames." );
         this.statusMessage = "measurement failed on all frames";
         failed = true;
      }

      let countString = WBPPUtils.resultCountToString( nCached, nMeasured, nFailed, "measured" );
      this.statusMessage = countString.length > 0 ? countString : framesToMeasure.length + " measured";
      this.hasWarnings = this.hasWarnings || nFailed > 0;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End generation of image descriptors" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();
      engine.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
      engine.processLogger.newLine();

      if ( failed )
         return OperationBlockStatus.FAILED;
      else
         return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to generate custom weights for frames based on quality metrics.
 * Uses configurable formula combining FWHM, SNR, stars etc.
 */
StackEngine.prototype.CustomFormulaWeightsGenerationOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Weights generation", undefined, true /* trackable */ );

   /**
    * data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Weights generation",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function()
   {
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Generate the custom formula weights" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();
      engine.processLogger.newLine();
      engine.processLogger.addMessage( "<b>*****************</b> <i>CUSTOM WEIGHTS GENERATION</i> <b>**************</b>" );

      // scan all groups and generate the formula weights, we skip fast integration groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive && !g.fastIntegrationData.enabled );

      let nGenerated = 0;
      let nFailed = 0;
      for ( let i = 0; i < groups.length; ++i )
      {
         let activeFrames = groups[ i ].activeFrames().filter( af => af.descriptor );
         let descriptors = activeFrames.map( frame => frame.descriptor ).filter( Boolean );
         let descriptorMinMax = engine.subframeAnalyzer.getMinMaxDescriptorsValues( descriptors );

         // pre-compute non normalized weights
         let scores = activeFrames.map( af =>
         {
            return engine.subframeAnalyzer.computeWeightForLight(
               af.descriptor,
               descriptorMinMax,
               engine.FWHMWeight,
               engine.eccentricityWeight,
               engine.SNRWeight,
               engine.starsWeight,
               engine.PSFSignalWeight,
               engine.PSFSNRWeight,
               engine.pedestal,
               1 /*normalization factor*/ ,
               false /* print to console */ );
         } );

         let normalizationFactor = Math.max.apply( null, scores.filter( score => isFinite( score ) ) );

         for ( let j = 0; j < activeFrames.length; ++j )
         {

            let descriptor = activeFrames[ j ].descriptor;

            let weight = engine.subframeAnalyzer.computeWeightForLight(
               descriptor,
               descriptorMinMax,
               engine.FWHMWeight,
               engine.eccentricityWeight,
               engine.SNRWeight,
               engine.starsWeight,
               engine.PSFSignalWeight,
               engine.PSFSNRWeight,
               engine.pedestal,
               normalizationFactor,
               true /* print to console */ );


            if ( isFinite( weight ) )
            {
               descriptor.imageWeight = weight;
               descriptor.formulaWeight = weight * normalizationFactor;
               nGenerated++;
            }
            else
            {
               console.warningln( "** Warning: Custom formula failed for frame: <raw>" + activeFrames[ j ].current + "</raw>" );
               activeFrames[ j ].processingFailed();
               nFailed++;
            }
         }
      }

      this.statusMessage = WBPPUtils.resultCountToString( 0 /* nCached */ , nGenerated, nFailed, "weight(s) generated" );
      this.hasWarnings = nFailed > 0;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End generation of image weights" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();


      if ( nFailed == 0 )
         engine.processLogger.addSuccess( "Success", nGenerated + " weight(s) generated" );
      else
         engine.processLogger.addWarning( this.statusMessage );
      engine.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
      engine.processLogger.newLine();

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to allow frame selection based on quality metrics.
 * In interactive mode, opens the WBPPFrameSelectionDialog for user to review and select frames.
 * In non-interactive mode, applies the default filter configuration to all groups automatically.
 * Frames rejected will be marked as failed and excluded from further processing.
 */
StackEngine.prototype.FrameSelectionOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Frame selection", undefined, true /* trackable */ );

   /**
    * Data for the event script
    */
   this.envForScript = () => (
   {
      name: "Frame selection",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   /**
    * Marks rejected frames as failed and logs them.
    * This is the operation-specific behavior after rejection state has been set
    * (either by the interactive dialog or by applying filter configurations).
    *
    * @param {FrameGroup} group - The group to process
    * @returns {number} Number of rejected frames
    */
   let markRejectedFramesAsFailed = function( group )
   {
      let rejectedCount = 0;
      let activeFrames = group.activeFrames();
      for ( let j = 0; j < activeFrames.length; j++ )
      {
         let frame = activeFrames[ j ];
         let descriptor = frame.descriptor;

         if ( descriptor && descriptor.rejected )
         {
            console.noteln( "  Rejected: " + File.extractNameAndExtension( frame.current || "" ) );
            frame.processingFailed();
            rejectedCount++;
         }
      }
      return rejectedCount;
   };

   this._run = function()
   {
      let isInteractive = engine.frameSelectionInteractive;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* " + ( isInteractive ? "Interactive" : "Automatic" ) + " frame selection" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();
      engine.processLogger.newLine();
      engine.processLogger.addMessage( "<b>*****************</b> <i>FRAME SELECTION</i> <b>***************</b>" );

      // Get all active post-process groups (POST groups are always LIGHT frames).
      // Exclude COMBINED_RGB groups - they are virtual groups for RGB recombination only,
      // without their own frames. Frame selection happens on the individual R, G, B channels.
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST )
         .filter( g => g.isActive && g.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB );

      if ( groups.length == 0 )
      {
         console.warningln( "** Warning: No active light frame groups to select from." );
         engine.processLogger.addWarning( "No active light frame groups to select from." );
         this.statusMessage = "no groups available";
         return OperationBlockStatus.CANCELED;
      }

      // Normalize PSFSignalWeight for each group: divide by max to get values in [0,1]
      // This is done per-group so each group has at least one frame with normalized value = 1
      for ( let i = 0; i < groups.length; i++ )
      {
         let group = groups[ i ];
         let activeFrames = group.activeFrames();
         let descriptors = activeFrames.map( f => f.descriptor ).filter( d => d != undefined );

         // Find max PSFSignalWeight for this group
         let psfswMax = 0;
         for ( let j = 0; j < descriptors.length; j++ )
         {
            if ( isFinite( descriptors[ j ].PSFSignalWeight ) && descriptors[ j ].PSFSignalWeight > psfswMax )
               psfswMax = descriptors[ j ].PSFSignalWeight;
         }

         // Add normalized value to each descriptor
         for ( let j = 0; j < descriptors.length; j++ )
         {
            if ( psfswMax > 0 && isFinite( descriptors[ j ].PSFSignalWeight ) )
               descriptors[ j ].PSFSignalWeightNormalized = descriptors[ j ].PSFSignalWeight / psfswMax;
            else
               descriptors[ j ].PSFSignalWeightNormalized = 0;
         }
      }

      let totalFrames = 0;
      let rejectedFrames = 0;
      let filterConfigs = null;

      if ( isInteractive )
      {
         // Interactive mode: open the frames selection dialog
         let dialog = new WBPPFrameSelectionDialog( groups );

         // Override the getActiveFramesForGroup method to return actual active frames with descriptors
         dialog.getActiveFramesForGroup = function( group )
         {
            if ( !group )
               return [];
            return group.activeFrames();
         };

         // Re-initialize with the override in place
         dialog.initialize();

         // Execute the dialog
         let result = dialog.execute();

         if ( result != StdDialogCode.Ok )
         {
            console.noteln( "Frame selection was canceled by user." );
            engine.processLogger.addWarning( "Frame selection was canceled by user." );
            this.statusMessage = "canceled by user";
            return OperationBlockStatus.CANCELED;
         }
         // Dialog has set rejection state on frames, filterConfigs remains null
      }
      else
      {
         // Non-interactive mode: validate and prepare filter configuration
         filterConfigs = engine.frameSelectionDefaultConfig;

         if ( !filterConfigs || filterConfigs.length == 0 )
         {
            console.noteln( "No default filter configuration defined. Skipping automatic frame selection." );
            engine.processLogger.addWarning( "No default filter configuration defined for automatic frame selection." );
            this.statusMessage = "no filter configuration";
            this.hasWarnings = true;
            return OperationBlockStatus.DONE;
         }

         // Check if any filter is actually enabled
         let hasEnabledFilters = filterConfigs.some( c => c.enabled );
         if ( !hasEnabledFilters )
         {
            console.noteln( "No filters enabled in default configuration. Skipping automatic frame selection." );
            engine.processLogger.addWarning( "No filters enabled in default configuration." );
            this.statusMessage = "no filters enabled";
            this.hasWarnings = true;
            return OperationBlockStatus.DONE;
         }

         console.noteln( "Applying default filter configuration to " + groups.length + " group(s)..." );
      }

      // Common processing: iterate through all groups and process rejections
      // In non-interactive mode, filters are applied first; in interactive mode,
      // the dialog has already set the rejection state
      for ( let i = 0; i < groups.length; i++ )
      {
         let group = groups[ i ];
         let groupFrames = group.activeFrames();
         totalFrames += groupFrames.length;

         console.noteln( "  Processing group: " + ( group.filter || "unfiltered" ) + " (" + groupFrames.length + " frames)" );

         if ( filterConfigs )
         {
            // non interactive mode: apply filters
            // Use centralized FrameGroup method to apply filters
            // This handles initialization, custom formula, and rejection state
            group.applyFilters( filterConfigs );
         }
         rejectedFrames += markRejectedFramesAsFailed( group );
      }

      // Set status message for execution monitor
      if ( rejectedFrames > 0 )
         this.statusMessage = rejectedFrames + " frame(s) rejected out of " + totalFrames;
      else
         this.statusMessage = totalFrames + " frame(s) processed, no rejections";

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End of frame selection" );
      console.noteln( "  Total frames: " + totalFrames );
      console.noteln( "  Rejected: " + rejectedFrames );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();

      // Always report success - rejecting frames is the expected behavior of this step
      engine.processLogger.addSuccess( "Frame selection completed", this.statusMessage );
      engine.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
      engine.processLogger.newLine();

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to reject low quality frames based on weights.
 * Filters frames that fall below minimum weight threshold.
 * Supports different weighting methods.
 */
StackEngine.prototype.BadFramesRejectionOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Bad frames rejection", undefined, true /* trackable */ );

   /**
    * data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Bad frames rejection",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   let _weightForFrame = function( activeFrame )
   {
      let descriptor = activeFrame.descriptor;
      if ( descriptor == undefined )
         return undefined;

      switch ( engine.subframesWeightsMethod )
      {
         case BPP.SubframeWeightsMethod.PSFSignal:
            return descriptor.PSFSignalWeight;
         case BPP.SubframeWeightsMethod.PSFSNR:
            return descriptor.PSFSNR;
         case BPP.SubframeWeightsMethod.PSFScaleSNR:
            return undefined;
         case BPP.SubframeWeightsMethod.SNREstimate:
            return descriptor.SNR;
         case BPP.SubframeWeightsMethod.FORMULA:
            return descriptor.imageWeight;
      }
      return undefined;
   }

   this._run = function()
   {

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Bad frames rejection" );
      console.noteln( BPP.Format.SEPARATOR );
      engine.processLogger.newLine();
      engine.processLogger.addMessage( "<b>*****************</b> <i>BAD FRAMES REJECTION</i> <b>**************</b>" );

      // we exclude fast integration groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive && !g.fastIntegrationData.enabled );
      let discardedFrames = 0;

      if ( engine.subframesWeightsMethod != BPP.SubframeWeightsMethod.PSFScaleSNR )
      {
         // using the active post-process groups

         for ( let i = 0; i < groups.length; ++i )
         {
            let group = groups[ i ];

            // we don't implement any frame rejection if fast integration is enabled
            if ( group.fastIntegrationData.enabled )
               continue;

            let activeFrames = group.activeFrames();

            // find the max value of the current weighting method
            let maxValue = activeFrames.reduce( ( value, frame ) =>
            {
               let weight = _weightForFrame( frame );

               if ( weight == undefined )
                  return value;

               return Math.max( weight, value );
            }, 0 );

            // if all weights are invalid then skip the group filtering
            if ( maxValue == 0 )
               continue;

            for ( let j = 0; j < activeFrames.length; ++j )
            {
               let normalizedWeight = ( _weightForFrame( activeFrames[ j ] ) || 0 ) / maxValue;
               let info = File.extractNameAndExtension( activeFrames[ j ].current )
                  + " - "
                  + format( "%.3f", normalizedWeight )
                  + ( normalizedWeight < engine.minWeight ? " < " : " > " )
                  + format( "%.3f", engine.minWeight )
                  + " | "
                  + ( normalizedWeight < engine.minWeight ? "rejected" : "accepted" );

               console.noteln( "[Frames rejection] ", info );
               if ( normalizedWeight < engine.minWeight )
               {
                  engine.processLogger.addWarning( "frame rejected [" + info + "]: " + activeFrames[ j ].current );
                  activeFrames[ j ].processingFailed();
                  discardedFrames++;
               }
            }
         }
      }

      this.statusMessage = discardedFrames + " rejected";

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End of bad frames rejection" );
      console.noteln( BPP.Format.SEPARATOR );

      engine.processLogger.addMessage( this.statusMessage );
      engine.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
      engine.processLogger.newLine();

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to select reference frames for registration.
 * Supports manual selection, auto selection and keyword-based selection.
 * Manages reference frame caching and reuse.
 */
StackEngine.prototype.ReferenceFrameSelectionOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Reference frame selection", undefined, true /* trackable */ );

   /**
    * data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Reference frame selection",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function( environment, requestInterruption )
   {
      let criticalErrorOccurred = false;

      engine.processLogger.newLine();
      engine.processLogger.addMessage( "<b>**********</b> <i>BEST REFERENCE FRAME FOR REGISTRATION</i> <b>***********</b>" );

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin selection of the best reference frame" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();

      // get the reference frame data from the environment
      // (see ReferenceFrameDataPreparationOperation for structure)
      let referenceFrameData = environment.referenceFrameData;

      // using the active post-process groups
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive );

      // initialize the reference frames per group ( only if mode is not cached, otherwise we keep it to reuse the same reference frame )
      if ( !engine.reuseLastReferenceFrames )
         for ( let i = 0; i < groups.length; ++i )
            groups[ i ].__reference_frame__ = undefined;
      if ( !engine.reuseLastLNReferenceFrames )
         for ( let i = 0; i < groups.length; ++i )
            groups[ i ].__ln_reference_frame__ = undefined;


      let nSelected = 0;
      let nFailed = 0;

      if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL )
      {
         // search in all files the selected frame, in case take as reference the
         // current processed file name
         console.noteln( "Best reference frame, manually selected: " + referenceFrameData[ "__manual__" ].referenceImage );
         engine.processLogger.addSuccess( "Best reference frame", " manually selected " + referenceFrameData[ "__manual__" ].referenceImage );

         // save reference frame for all groups
         for ( let i = 0; i < groups.length; ++i )
            groups[ i ].__reference_frame__ = referenceFrameData[ "__manual__" ].referenceImage;
         this.statusMessage = "Manual";
      }
      else
      {
         if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.AUTO_SINGLE )
         {
            let actualReferenceImage = engine.subframeAnalyzer.findRegistrationReferenceFileItem( referenceFrameData[ "__single__" ].groups );
            if ( actualReferenceImage )
            {
               console.noteln( "Best reference frame for registration - auto selection completed: " + actualReferenceImage.current );
               engine.processLogger.addSuccess( "Best reference frame", " (auto selection) " + actualReferenceImage.current );

               // save reference frame for all groups
               for ( let i = 0; i < groups.length; ++i )
                  groups[ i ].__reference_frame__ = actualReferenceImage.current;

               // mark the frame as reference
               actualReferenceImage.markAsReference();
               nSelected++;
            }
            else
            {
               // mark all frames as failed
               for ( let i = 0; i < groups.length; ++i )
               {
                  let activeFrames = groups[ i ].activeFrames();
                  for ( let j = 0; j < activeFrames.length; ++j )
                     activeFrames[ j ].processingFailed();
               }

               console.criticalln( "*** Error: Unable to detect the best reference frame." );
               engine.processLogger.addError( "Unable to detect the best reference frame." );
               this.statusMessage = "failed to detect the reference frame";
               criticalErrorOccurred = true;
            }
         }
         else
         {
            let keywordsFailed = [];
            let referenceFrameDataKeys = Object.keys( referenceFrameData );
            referenceFrameData = referenceFrameDataKeys.reduce( ( acc, keywordValue ) =>
            {
               let data = referenceFrameData[ keywordValue ];
               let actualReferenceImage = engine.subframeAnalyzer.findRegistrationReferenceFileItem( data.groups );
               console.noteln( "<end><cbr><br>" );
               if ( actualReferenceImage )
               {
                  console.noteln( "Best reference frame for " + engine.bestFrameReferenceKeyword + " = " + keywordValue + " : " + actualReferenceImage.current );
                  engine.processLogger.addSuccess( "Best reference frame for " + engine.bestFrameReferenceKeyword + " = " + keywordValue, actualReferenceImage.current );

                  // store the reference image in the current groups per keyword
                  for ( let i = 0; i < data.groups.length; ++i )
                     data.groups[ i ].__reference_frame__ = actualReferenceImage.current;

                  // mark the frame as reference
                  actualReferenceImage.markAsReference();
                  nSelected++;
               }
               else
               {
                  // mark all frames in the current goups per keyword as failed
                  for ( let i = 0; i < data.groups.length; ++i )
                  {
                     let activeFrames = data.groups[ i ].activeFrames();
                     for ( let j = 0; j < activeFrames.length; ++j )
                        activeFrames[ j ].processingFailed();
                  }

                  let msg = "Unable to detect the best reference frame for " + engine.bestFrameReferenceKeyword + " = " + keywordValue
                     + ". Groups with this key/value will not be registered.";
                  console.criticalln( "*** Error: " + msg );
                  engine.processLogger.addError( msg );
                  keywordsFailed.push( keywordValue );
                  nFailed++;
               }
               return acc;
            },
            {} );

            if ( keywordsFailed.length == referenceFrameDataKeys.length )
            {
               this.statusMessage = "failed to detect all reference frames";
               criticalErrorOccurred = true;
            }
            else if ( keywordsFailed.length > 0 )
            {
               let last = keywordsFailed.pop();
               let commaSeparatedList = keywordsFailed.join( ", " ) + ( keywordsFailed.length > 0 ? " and " : "" ) + last;
               this.statusMessage = "failed to assign a reference frame for " + commaSeparatedList + " keyword" + ( keywordsFailed.length > 1 ? "s" : "" );
               this.hasWarnings = true;
            }

            console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
            console.noteln( "* End selection of the best reference frame" );
            console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
            console.flush();

            this.statusMessage = nSelected + " frame(s) selected";
            if ( nFailed > 0 )
               this.statusMessage += ", " + nFailed + " failed";
         }
      }

      engine.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
      engine.processLogger.newLine();

      if ( criticalErrorOccurred )
      {
         requestInterruption();
         return OperationBlockStatus.CANCELED;
      }

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to register (align) frames to reference frame.
 * Uses star matching and geometric transformation.
 * Supports distortion correction and generates drizzle data.
 */
StackEngine.prototype.RegistrationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Registration", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      return frameGroup.groupSize();
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Registration",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin registration of light frames" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();
      console.flush();

      let activeFrames = frameGroup.activeFrames();

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active light frames to be registered." );
         engine.processLogger.addError( "No active light frames to be registered." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }

      console.noteln( "<br>Reference image: ", frameGroup.__reference_frame__ );
      engine.processLogger.addSuccess( "Reference image", frameGroup.__reference_frame__ );

      let subfolder = frameGroup.folderName();
      let registerDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/registered/" + subfolder );
      let filePaths = activeFrames.map( item => item.current );

      let SA = new StarAlignment;
      SA.inputHints = engine.imageProcessor.inputHints();
      SA.outputHints = engine.imageProcessor.outputHints();
      SA.referenceImage = frameGroup.__reference_frame__;
      SA.referenceIsFile = true;
      SA.outputDirectory = registerDirectory;
      SA.generateDrizzleData = true;
      SA.pixelInterpolation = engine.pixelInterpolation;
      SA.clampingThreshold = engine.clampingThreshold;
      SA.structureLayers = engine.structureLayers;
      SA.hotPixelFilterRadius = engine.hotPixelFilterRadius;
      SA.noiseReductionFilterRadius = engine.noiseReductionFilterRadius;
      SA.minStructureSize = engine.minStructureSize;
      SA.sensitivity = engine.sensitivity;
      SA.peakResponse = engine.peakResponse;
      SA.brightThreshold = engine.brightThreshold;
      SA.maxStarDistortion = engine.maxStarDistortion;
      SA.allowClusteredSources = engine.allowClusteredSources;
      SA.useTriangles = engine.useTriangleSimilarity;
      SA.outputExtension = ".xisf";
      SA.outputPrefix = "";
      SA.outputPostfix = "_r";
      SA.outputSampleFormat = StarAlignment.f32;
      SA.overwriteExistingFiles = false;
      SA.inheritAstrometricSolution = true;
      SA.rigidTransformations = engine.rigidTransformations;

      // Override star alignment parameters if the current group is a separated RGB channel
      if ( engine.distortionCorrection || frameGroup.associatedRGBchannel != undefined )
      {
         SA.distortionCorrection = true;
         SA.rbfType = StarAlignment.DDMThinPlateSpline;
         SA.maxSplinePoints = 4000;
         SA.splineOrder = 2;
      }
      else
         SA.maxStars = engine.maxStars;

      if ( frameGroup.associatedRGBchannel != undefined )
         SA.noiseReductionFilterRadius = Math.max( 2, engine.noiseReductionFilterRadius );

      let SASource = SA.toSource( "JavaScript", "SA" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
      console.writeln( BPP.Format.SEPARATOR2 );
      console.writeln( SASource );
      console.writeln( BPP.Format.SEPARATOR2 );

      /*
       * Skip alignment for files that have valid cached data. Cache is a map between an input file and an
       * output file:
       * [inputFile]: outputFile
       */
      let filesToRegister = filePaths;
      let cachedCount = 0;
      let cached = {};
      let SACache = {};
      let SAcacheKey = engine.executionCache.keyFor( SASource );
      if ( engine.executionCache.hasCacheForKey( SAcacheKey ) )
      {
         console.noteln( "StarAlignment: cache data for key ", SAcacheKey );

         if ( engine.executionCache.isFileUnmodified( SAcacheKey, frameGroup.__reference_frame__ ) )
         {
            // Star Alignment has already been executed with such configuration and the registered frame is unchanged.
            // We avoid to align frames that have already been processed by this configuration.
            // The cache data is a map between input and output (registered) file, if both are unchanged then
            // we remove them from the list of the files to be aligned.
            filesToRegister = [];
            SACache = engine.executionCache.cacheForKey( SAcacheKey );
            for ( let i = 0; i < filePaths.length; ++i )
            {
               let inputFile = filePaths[ i ];
               let outputFile = SACache[ inputFile ];
               let drizzleFilePath = outputFile != undefined ? File.changeExtension( outputFile, ".xdrz" ) : "";

               if ( outputFile != undefined
                  && engine.executionCache.isFileUnmodified( SAcacheKey, inputFile )
                  && engine.executionCache.isFileUnmodified( SAcacheKey, outputFile )
                  && engine.executionCache.isFileUnmodified( SAcacheKey, drizzleFilePath )
               )
               {
                  console.noteln( "StarAlignment: cache ", inputFile, " --> ", outputFile );
                  cached[ inputFile ] = outputFile;
                  cachedCount++;
               }
               else
               {
                  console.noteln( "StarAlignment: align ", inputFile );
                  filesToRegister.push( inputFile );
               }
            }
         }
         else
         {
            console.noteln( "StarAlignment: reference frame has changed, ignore cache and register all frames." );
         }
      }
      else
      {
         console.noteln( "StarAlignment: no cache data for key ", SAcacheKey );
      }

      // in process container we store the full SA measured files
      SA.targets = WBPPUtils.enableTargetFrames( filePaths, 3 );
      engine.processContainer.add( SA );
      engine.pipelineManager.flushProcessContainer();

      // set the files to be measured and proceed
      let success = true;
      if ( filesToRegister.length > 0 )
      {
         SA.targets = WBPPUtils.enableTargetFrames( filesToRegister, 3 );
         success = SA.executeGlobal();
         engine.executionCache.cacheFileLMD( SAcacheKey, frameGroup.__reference_frame__ );
      }

      if ( !success && cachedCount == 0 )
      {
         // critical error, the output data must always have the same size of the input data
         // mark all active frames as failed
         activeFrames.forEach( activeFrame => activeFrame.processingFailed() );
         // report the issue
         console.warningln( "** Warning: Error registering light frames. This group will be skipped." );
         engine.processLogger.addError( "Error registering light frames. This group will be skipped." );
         this.statusMessage = "registration failed";
         return OperationBlockStatus.FAILED;
      }

      if ( filesToRegister.length > 0 && cachedCount == 0 )
         if ( !SA.outputData || SA.outputData.length != filesToRegister.length )
         {
            // critical error, the output data must always have the same size of the input data
            // mark all active frames as failed
            activeFrames.forEach( activeFrame => activeFrame.processingFailed() );
            // report the issue
            console.warningln( "** Warning: Light frames registration failed: the output data size mismatches the input data size." );
            engine.processLogger.addError( "Light frames registration failed: output data size mismatch." );
            this.statusMessage = "a critical error occurred (data size mismatch).";
            return OperationBlockStatus.FAILED;
         }

      // create a support for output file matching
      let registeredFiles = SA.outputData.map( outputItem => outputItem[ 0 ] );

      let nCached = 0;
      let nRegistered = 0;
      let nFailed = 0;

      // scan all input files and detect the corresponding registered version
      let j = 0;
      for ( let c = 0; c < activeFrames.length; ++c )
      {
         let inputFile = filePaths[ c ];
         let outputFile;
         let cachedFile = false;

         // input file may be mapped in the cache or picked from the SA output list (if not cached)
         if ( cached[ inputFile ] != undefined )
         {
            cachedFile = true;
            outputFile = cached[ inputFile ];
         }
         else
            // just aligned
            outputFile = registeredFiles[ j++ ];

         let errorMsg = "";
         let success = false;

         if ( outputFile )
         {
            if ( outputFile.length > 0 )
            {
               if ( File.exists( outputFile ) )
               {
                  success = true;
                  activeFrames[ c ].processingSucceeded( BPP.FrameProcessingStep.REGISTRATION, outputFile );

                  // store the drizzle file if present
                  let drizzleFilePath = File.changeExtension( outputFile, ".xdrz" );
                  if ( File.exists( drizzleFilePath ) )
                     activeFrames[ c ].addDrizzleFile( drizzleFilePath );

                  // cache the input and output file data if not already cached
                  if ( !cachedFile )
                  {
                     SACache[ inputFile ] = outputFile;
                     engine.executionCache.cacheFileLMD( SAcacheKey, inputFile );
                     engine.executionCache.cacheFileLMD( SAcacheKey, outputFile );
                     engine.executionCache.cacheFileLMD( SAcacheKey, drizzleFilePath );
                  }

                  if ( cachedFile )
                     nCached++;
                  else
                     nRegistered++;
               }
               else
               {
                  errorMsg = ": Registered frame not found " + outputFile;
                  engine.processLogger.addWarning( "File does not exist after image registration: " + outputFile );
                  activeFrames[ c ].processingFailed();
                  nFailed++;
               }
            }
            else
            {
               errorMsg = ": output file name is an empty string";
               engine.processLogger.addWarning( "Registration failed for image: " + inputFile );
               activeFrames[ c ].processingFailed();
               nFailed++;
            }
         }
         else
         {
            errorMsg = ": Empty output file name";
            engine.processLogger.addWarning( "Registration failed for image: " + inputFile );
            activeFrames[ c ].processingFailed();
            nFailed++;
         }

         if ( success )
            console.writeln( "Registered frame " + c + ": <raw>" + inputFile + "</raw> ---> <raw>" + outputFile + "</raw>" );
         else
            console.warningln( "** Warning: Registered frame " + c + ": <raw>" + inputFile + "</raw> ---> [ FAILED" + errorMsg + " ]" );
      }

      // update the cache for this Star Alignment configuration
      engine.executionCache.setCache( SAcacheKey, SACache );

      let registeredFrames = frameGroup.activeFrames();
      if ( registeredFrames.length < 1 )
      {
         console.warningln( "** Warning: No light frames found after registration." );
         engine.processLogger.addError( "No light frames found after registration." );
         this.statusMessage = "no light frames found after registration";
         return OperationBlockStatus.FAILED;
      }

      engine.processLogger.addSuccess( "Registration completed", registeredFrames.length + " images out of " + activeFrames.length + " successfully registered." );

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End registration of light frames" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();

      this.statusMessage = WBPPUtils.resultCountToString( nCached, nRegistered, nFailed, "registered" );
      this.hasWarnings = nFailed > 0;

      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to select reference frames for local normalization.
 * Supports interactive selection and automatic generation methods.
 */
StackEngine.prototype.LocalNormalizationReferenceFrameSelectionOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      let title = "";
      let trackable = false;
      if ( engine.localNormalizationInteractiveMode )
      {
         title = "LN reference [interactive]";
         trackable = true;
      }
      else if ( engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.INTEGRATION_BEST_FRAMES )
      {
         title = "LN reference generation";
         trackable = true;
      }
      else
      {
         trackable = false;
      }
      super( title, frameGroup, trackable );

   this.spaceRequired = () =>
   {
      return frameGroup.frameSize();
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: title,
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function( environment )
   {
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Local normalization reference frame selection" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();
      console.flush();

      let activeFrames = frameGroup.activeFrames();

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active light frames to be locally normalized." );
         engine.processLogger.addError( "No active light frames to be locally normalized." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }

      if ( engine.localNormalizationInteractiveMode )
      {
         console.noteln( "-" );
         console.noteln( "STARTING Local Normalization Interactive Session" );
         console.noteln( "-" );
         engine.operationQueue.hideExecutionMonitorDialog();
         let LNReferenceFrameSelectionWindow = new WBPPLocalNormalizationReferenceSelector( frameGroup );
         LNReferenceFrameSelectionWindow.execute();
         console.noteln( "-" );
         console.noteln( "Local Normalization Interactive Session TERMINATED" );
         console.noteln( "-" );
         let lnReferenceFrame = LNReferenceFrameSelectionWindow.referenceFrame;


         if ( lnReferenceFrame == undefined )
         {
            console.warningln( "** Warning: Unable to find the reference frame generated during the interactive mode." );
            engine.processLogger.addError( "Unable to find the reference frame generated during the interactive mode." );
            this.statusMessage = "no reference frame defined";
            return OperationBlockStatus.FAILED;
         }

         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* End selection of local normalization reference frame" );
         console.noteln( BPP.Format.SEPARATOR );
         console.flush();

         // inject the reference frame in the environment
         frameGroup.__ln_reference_frame__ = lnReferenceFrame;
         return OperationBlockStatus.DONE;
      }
      else
      {
         // select the reference frame
         let
         {
            lnReferenceFilePath,
            cached
         } = engine.imageProcessor.generateLNReference( frameGroup );

         if ( lnReferenceFilePath == undefined )
         {
            console.warningln( "** Warning: Unable to determine the local normalization reference frame. "
               + "Local normalization will be skipped for this group." );
            engine.processLogger.addError( "Unable to determine the local normalization reference frame. "
               + "Local normalization will be skipped for this group." );
            this.statusMessage = "unable to find a local normalization reference frame";
            return OperationBlockStatus.FAILED;
         }

         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* End selection of local normalization reference frame" );
         console.noteln( BPP.Format.SEPARATOR );
         console.flush();

         // inject the reference frame in the environment
         frameGroup.__ln_reference_frame__ = lnReferenceFilePath;
         if ( cached )
            this.statusMessage = "cached";
         return OperationBlockStatus.DONE;
      }
   };
   }
};

/**
 * Operation to apply local normalization to registered frames.
 */
StackEngine.prototype.LocalNormalizationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Local Normalization", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      if ( engine.localNormalizationGenerateImages )
      {
         return frameGroup.groupSize();
      }
      else
      {
         return 0;
      }
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Local Normalization",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function( environment )
   {
      let failed = false;

      let activeFrames = frameGroup.activeFrames();

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active light frames to be locally normalized." );
         engine.processLogger.addError( "No active light frames to be locally normalized." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }

      // select the reference frame
      let lnReferenceFrame = frameGroup.__ln_reference_frame__;

      if ( lnReferenceFrame == undefined )
      {
         console.warningln( "** Warning: Unable to determine the local normalization reference frame. "
            + "Local normalization will be skipped for this group." );
         engine.processLogger.addError( "Unable to determine the local normalization reference frame. "
            + "Local normalization will be skipped for this group." );
         this.statusMessage = "unable to find a local normalization reference frame";
         return OperationBlockStatus.FAILED;
      }

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin local normalization of light frames" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();
      console.flush();

      console.noteln( "* Local normalization reference image: <raw>" + lnReferenceFrame + "</raw>" );
      engine.processLogger.addSuccess( "Local normalization reference image", lnReferenceFrame );

      let referenceImageSize = WBPPUtils.getImageSize( lnReferenceFrame );
      let imageRefrenceDimension = Math.min( referenceImageSize.width, referenceImageSize.height );

      let LN = new LocalNormalization;
      LN.overwriteExistingFiles = true;
      let filePaths = activeFrames.map( item => item.current );
      LN.referencePathOrViewId = lnReferenceFrame;
      LN.referenceIsView = false;
      LN.scale = imageRefrenceDimension / engine.localNormalizationGridSize;
      LN.referenceRejectionThreshold = 3.00;
      LN.targetRejectionThreshold = 3.20;
      LN.psfMaxStars = engine.localNormalizationPsfMaxStars;
      LN.psfMinSNR = engine.localNormalizationPsfMinSNR;
      LN.psfAllowClusteredSources = engine.localNormalizationPsfAllowClusteredSources;
      LN.lowClippingLevel = engine.localNormalizationLowClippingLevel;
      LN.highClippingLevel = engine.localNormalizationHighClippingLevel;
      LN.scaleEvaluationMethod = ( engine.localNormalizationMethod == 0 )
         ? LocalNormalization.ScaleEvaluationMethod_PSFSignal
         : LocalNormalization.ScaleEvaluationMethod_MultiscaleAnalysis;
      LN.psfType = [
         LocalNormalization.PSFType_Gaussian,
         LocalNormalization.PSFType_Moffat15,
         LocalNormalization.PSFType_Moffat4,
         LocalNormalization.PSFType_Moffat6,
         LocalNormalization.PSFType_Moffat8,
         LocalNormalization.PSFType_MoffatA,
         LocalNormalization.PSFType_Auto
      ][ engine.localNormalizationPsfType ];
      LN.psfGrowth = engine.localNormalizationPsfGrowth;

      if ( engine.localNormalizationGenerateImages )
         LN.generateNormalizedImages = LocalNormalization.GenerateNormalizedImages_Always;

      // Since core version 1.8.9-1, LocalNormalization can generate .xnml
      // tagged as invalid when relative scale factor evaluation fails. These
      // special files are recognized by ImageIntegration and the corresponding
      // images are excluded from the integration. This allows us to be
      // tolerant of normalization errors.
      LN.generateInvalidData = true;

      let LNSource = LN.toSource( "JavaScript", "LN" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();

      // Check if valid cached data is present
      let filesToNormalize = filePaths;
      let cachedCount = 0;
      let cached = {};
      let LNCache = {};
      let LNcacheKey = engine.executionCache.keyFor( LNSource );
      if ( engine.executionCache.hasCacheForKey( LNcacheKey ) )
      {
         console.noteln( "Local Normalization has cached data for key ", LNcacheKey );

         if ( engine.executionCache.isFileUnmodified( LNcacheKey, LN.referencePathOrViewId ) )
         {
            // valid cache found. The cache is a map between the input file and the output LN file
            console.noteln( "Local Normalization has cached data for key ", LNcacheKey );

            LNCache = engine.executionCache.cacheForKey( LNcacheKey );
            filesToNormalize = [];

            for ( let i = 0; i < filePaths.length; ++i )
            {
               let inputFile = filePaths[ i ];
               let lnFile = LNCache[ inputFile ];
               if ( lnFile != undefined
                  && engine.executionCache.isFileUnmodified( LNcacheKey, inputFile )
                  && engine.executionCache.isFileUnmodified( LNcacheKey, lnFile ) )
               {
                  cached[ inputFile ] = lnFile;
                  cachedCount++;
                  console.noteln( "Local Normalization cache for input found: ", inputFile, " --> ", lnFile );
               }
               else
               {
                  filesToNormalize.push( inputFile );
                  console.noteln( "Local Normalization input file will be normalized: ", inputFile );
               }
            }
         }
      }
      else
      {
         console.noteln( "Local Normalization has no cached data for key ", LNcacheKey );
      }

      // write the process into the console
      console.writeln( BPP.Format.SEPARATOR2 );
      console.writeln( LNSource );
      console.writeln( BPP.Format.SEPARATOR2 );

      // process is saved in container with the full list of files to be normalized
      LN.targetItems = WBPPUtils.enableTargetFrames( filePaths, 2 );
      engine.processContainer.add( LN );
      engine.pipelineManager.flushProcessContainer();

      // perform LN if there are files to normalize
      let success = true;
      if ( filesToNormalize.length > 0 )
      {
         LN.targetItems = WBPPUtils.enableTargetFrames( filesToNormalize, 2 );
         success = LN.executeGlobal();
         engine.executionCache.cacheFileLMD( LNcacheKey, LN.referencePathOrViewId );
      }

      let nCached = 0;
      let nSuccess = 0;
      let nFailed = 0;

      if ( !success && cachedCount == 0 )
      {
         console.warningln( "** Warning: Error applying local normalization to light frames. This group will be skipped." );
         engine.processLogger.addError( "Error applying local normalization to light frames. This group will be skipped." );
         failed = true;
      }
      else if ( filesToNormalize.length > 0 && cachedCount == 0 && ( !LN.outputData || LN.outputData.length != filesToNormalize.length ) )
      {
         // skip local normalization
         console.warningln( "** Warning: Local normalization issue occurred. Local normalization will not be applied." );
         engine.processLogger.addWarning( "Local normalization issue occurred. Local normalization will not be applied" );
         failed = true;
      }
      else
      {
         let lnFiles = [];
         let j = 0;
         for ( let i = 0; i < filePaths.length; ++i )
         {
            let inputFile = filePaths[ i ];
            if ( cached[ inputFile ] != undefined )
            {
               lnFiles.push(
               {
                  path: cached[ inputFile ],
                  valid: true,
                  cached: true
               } );
            }
            else
            {
               let lnFile = LN.outputData[ j++ ];
               lnFiles.push(
               {
                  path: lnFile[ 0 ] || "",
                  valid: lnFile[ 5 ] || false,
                  cached: false
               } );
            }
         }

         // ensure that valid LN files have been created for each file
         for ( let k = 0; k < lnFiles.length; ++k )
         {
            if ( lnFiles[ k ].path.length == 0 )
            {
               console.warningln( "** Warning: Local normalization generation failed for file: <raw>" + activeFrames[ k ].current + "</raw>" );
               engine.processLogger.addWarning( "Local normalization failed for file: " + activeFrames[ k ].current );
               activeFrames[ k ].processingFailed();
               nFailed++;
            }
            else if ( !File.exists( lnFiles[ k ].path ) )
            {
               console.warningln( "** Warning: Local normalization data file not found for file: <raw>" + activeFrames[ k ].current + "</raw>" );
               engine.processLogger.addWarning( "Local normalization data file not found for file: " + activeFrames[ k ].current );
               activeFrames[ k ].processingFailed();
               nFailed++;
            }
            else
            {
               if ( !lnFiles[ k ].valid )
               {
                  console.warningln( "** Warning: Invalid local normalization data generated for file: <raw>" + activeFrames[ k ].current + "</raw>" );
                  engine.processLogger.addWarning( "Invalid local normalization data generated for file: " + activeFrames[ k ].current );
                  activeFrames[ k ].processingFailed();
                  nFailed++;
               }
               else
               {
                  // valid LN files are cached
                  LNCache[ filePaths[ k ] ] = lnFiles[ k ].path;
                  engine.executionCache.cacheFileLMD( LNcacheKey, filePaths[ k ] );
                  engine.executionCache.cacheFileLMD( LNcacheKey, lnFiles[ k ].path );
                  activeFrames[ k ].addLocalNormalizationFile( lnFiles[ k ].path );
                  if ( lnFiles[ k ].cached )
                     nCached++;
                  else
                     nSuccess++;
               }
            }
         }
         // save the updated cache
         engine.executionCache.setCache( LNcacheKey, LNCache );

      }

      engine.processLogger.addSuccess( "Local normalization", "completed." );
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End local normalization of light frames" );
      console.noteln( BPP.Format.SEPARATOR );
      console.flush();

      this.statusMessage = WBPPUtils.resultCountToString( nCached, nSuccess, nFailed, "completed" );
      this.hasWarnings = nFailed > 0;
      if ( failed )
         return OperationBlockStatus.FAILED;
      else
         return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to integrate (stack) aligned frames.
 */
StackEngine.prototype.ImageIntegrationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Integration", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      return engine.generateRejectionMaps ? frameGroup.frameSize() * 3 : frameGroup.frameSize();
   }

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Integration",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      let activeFrames = frameGroup.activeFrames();

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active frames to be integrated." );
         engine.processLogger.addError( "No active frames to be integrated." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }

      if ( activeFrames.length < 3 )
      {
         console.warningln( "** Warning: Less than 3 frames to integrate." );
         engine.processLogger.addError( "Less than 3 frames to integrate." );
         this.statusMessage = "only " + activeFrames.length + " active frames";
         return OperationBlockStatus.CANCELED;
      }

      let groupType = StackEngine.imageTypeToString( frameGroup.imageType );

      // we store the xnml and xdrz file LMD to check if they have been updated after the integration, if needed
      let LMDs = {};

      if ( frameGroup.isDrizzleEnabled() )
         for ( let i = 0; i < activeFrames.length; ++i )
         {
            let drizzleFile = activeFrames[ i ].drizzleFile;
            if ( drizzleFile != undefined )
               LMDs[ drizzleFile ] = WBPPUtils.getLastModifiedDate( drizzleFile );
         }

      // do integrate
      // overscan-specific intervention: when we integrate a master flat and the overscan is enabled we
      // store two custon keywords to remind the original frame sizes, this will help the matching and the addition
      // of this special cropped master
      let keywords = [];
      if ( frameGroup.imageType == ImageType.Flat && engine.overscan.enabled )
      {
         keywords.push( new FITSKeyword( "PREOVSCW", format( "%d", frameGroup.size.width ), "Width of the original flat frames before overscan" ) );
         keywords.push( new FITSKeyword( "PREOVSCH", format( "%d", frameGroup.size.height ), "Height of the original flat frames before overscan" ) );
      }
      let
      {
         masterFilePath,
         cached,
         numberOfImages
      } = engine.imageProcessor.doIntegrate(
         frameGroup,
         undefined /* custom prefix */ ,
         undefined /* custom postfix */ ,
         undefined /* customGenerateRejectionMaps */ ,
         undefined /* customGenerateDrizzle */ ,
         undefined /* desiredFileName */ ,
         {} /* overrideIIparameters */ ,
         keywords
      );

      // check the result
      if ( WBPPUtils.isEmptyString( masterFilePath ) )
      {
         console.warningln( "** Warning: Master " + groupType + " file was not generated." );
         engine.processLogger.addError( "Warning: Master " + groupType + " file was not generated." );
         this.statusMessage = "master file not generated";
         return OperationBlockStatus.FAILED;
      }

      if ( frameGroup.imageType != ImageType.Light )
      {
         // add the created master file
         console.writeln( "Add the master file: <raw>" + masterFilePath + "</raw>" );
         engine.addFile( masterFilePath );
      }
      else
      {
         // store the master file associated to the group ID into the environment for further processing
         // this info is used, for example, by channel recombination
         console.writeln( "Set the group's master file: <raw>" + masterFilePath + "</raw>" );
         frameGroup.setMasterFileName( masterFilePath );

         // we disable the light frame if the xnml files are supposed to be updated but are unchanged after integration
         // but drizzle integration is enabled, in this case the drizzle integration would complain that no
         // normalization information is present, so we set the light frame as failed.
         // this may only happen if the frame has not been integrated because of the low weight.
         if ( !cached && frameGroup.isDrizzleEnabled() )
            for ( let i = 0; i < activeFrames.length; ++i )
            {
               let drizzleFile = activeFrames[ i ].drizzleFile;
               if ( LMDs[ drizzleFile ] == WBPPUtils.getLastModifiedDate( drizzleFile ) )
               {
                  activeFrames[ i ].processingFailed();
                  console.writeln( "Drizzle data for frame <raw>" + activeFrames[ i ].fileItem.filePath + "</raw> has not been updated." )
               }
            }
      }

      engine.processLogger.addSuccess( "Integration completed", "master " + groupType + " saved at path " + masterFilePath );
      this.statusMessage = "" + numberOfImages + ( cached ? " cached" : " integrated" );
      console.noteln( "numberOfImages: ", numberOfImages );
      if ( numberOfImages < activeFrames.length )
         this.statusMessage += ( this.statusMessage.length > 0 ? ", " : "" ) + ( activeFrames.length - numberOfImages ) + " rejected";
      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation for fast integration of frames.
 * Provides quicker stacking for time-sensitive processing.
 * Uses simplified integration methods with basic rejection.
 */
StackEngine.prototype.FastIntegrationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Fast Integration", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      if ( frameGroup.fastIntegrationSaveImageEnabled() )
         return frameGroup.frameSize() * frameGroup.fileItems.length;
      else
         return 0;
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "FastIntegration",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      let activeFrames = frameGroup.activeFrames();

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active frames to be integrated." );
         engine.processLogger.addError( "No active frames to be integrated." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }

      let groupType = StackEngine.imageTypeToString( frameGroup.imageType );

      // we store the xnml and xdrz file LMD to check if they have been updated after the integration, if needed
      let LMDs = {};

      if ( frameGroup.isDrizzleEnabled() )
         for ( let i = 0; i < activeFrames.length; ++i )
         {
            let drizzleFile = activeFrames[ i ].drizzleFile;
            if ( drizzleFile != undefined )
               LMDs[ drizzleFile ] = WBPPUtils.getLastModifiedDate( drizzleFile );
         }

      let
      {
         masterFilePath,
         cached,
         numberOfImages
      } = engine.imageProcessor.doFastIntegration(
         frameGroup,
         frameGroup.__reference_frame__
      );

      // check the result
      if ( WBPPUtils.isEmptyString( masterFilePath ) )
      {
         console.warningln( "** Warning: Master " + groupType + " file was not generated." );
         engine.processLogger.addError( "Warning: Master " + groupType + " file was not generated." );
         this.statusMessage = "master file not generated";
         return OperationBlockStatus.FAILED;
      }

      // store the master file associated to the group ID into the environment for further processing
      // this info is used, for example, by channel recombination
      console.writeln( "Set the group's master file: <raw>" + masterFilePath + "</raw>" );
      frameGroup.setMasterFileName( masterFilePath );

      engine.processLogger.addSuccess( "Fast integration completed (" + numberOfImages + " of " + activeFrames.length + " integrated)", "master " + groupType + " saved at path " + masterFilePath );
      this.statusMessage = "" + numberOfImages + ( cached ? " cached" : " integrated" );
      console.noteln( "numberOfImages: ", numberOfImages );
      if ( numberOfImages < activeFrames.length )
         this.statusMessage += ( this.statusMessage.length > 0 ? ", " : "" ) + ( activeFrames.length - numberOfImages ) + " failed";
      this.hasWarnings = activeFrames.length != numberOfImages;
      return OperationBlockStatus.DONE;
   };
   }
};


/**
 * Operation to perform drizzle integration of frames.
 */
StackEngine.prototype.DrizzleIntegrationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Drizzle Integration (" + frameGroup.drizzleScale() + "x)" + ( frameGroup.drizzleFast() ? " Fast" : "" ), frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      return frameGroup.frameSize() * frameGroup.drizzleScale() * frameGroup.drizzleScale();
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Drizzle Integration",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function( environment )
   {
      let activeFrames = frameGroup.activeFrames();

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin drizzle integration of ", StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      if ( activeFrames.length == 0 )
      {
         console.warningln( "** Warning: No active frames; drizzle integration skipped." );
         engine.processLogger.addError( "No active frames; drizzle integration skipped." );
         this.statusMessage = "no active frames";
         return OperationBlockStatus.CANCELED;
      }
      else
      {
         // we proceed with drizzle integration only if image integration has succeeded
         let masterFileName = frameGroup.getMasterFileName();
         if ( masterFileName == undefined || !File.exists( masterFileName ) )
         {
            console.warningln( "** Warning: No active master light has been generated. Drizzle integration is skipped." );
            engine.processLogger.addError( "No active master light has been generated. Drizzle integration is skipped." );
            this.statusMessage = "no master light found";
            return OperationBlockStatus.CANCELED;
         }
      }

      let groupType = StackEngine.imageTypeToString( frameGroup.imageType );

      // apply drizzle integration

      let
      {
         masterFilePath,
         cached
      } = engine.imageProcessor.doDrizzleIntegration(
         frameGroup,
         frameGroup.drizzleFast() /* fast */ ,
         frameGroup.drizzleScale() /* scale */ ,
         frameGroup.drizzleDropShrink() /* shrink */ ,
         frameGroup.drizzleFunction() /* kernel */ ,
         undefined /* custom prefix */ ,
         "_drizzle_" + frameGroup.drizzleScale() + "x" /* custom postfix */ ,
         undefined /* desiredFileName */ ,
         undefined /* overrideDIparameters */ ,
         [] /* keywords */
      );

      // check the result
      if ( WBPPUtils.isEmptyString( masterFilePath ) || !File.exists( masterFilePath ) )
      {
         console.warningln( "** Warning: Master " + groupType + " file was not generated." );
         engine.processLogger.addError( "Warning: Master " + groupType + " file was not generated." );
         this.statusMessage = "master file not generated";
         return OperationBlockStatus.FAILED;
      }

      if ( frameGroup.imageType != ImageType.Light )
         // add the created master file
         engine.addFile( masterFilePath );
      else
         // store the master file associated to the group ID into the environment for further processing
         // this info is used, for example, by channel recombination
         frameGroup.setMasterFileName( masterFilePath, BPP.MasterType.DRIZZLE );


      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End drizzle integration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      engine.processLogger.addSuccess( "Drizzle Integration completed", "master " + groupType + " saved at path " + masterFilePath );
      this.statusMessage = cached ? "cached" : "";
      return OperationBlockStatus.DONE;
   };
   }
};

/**
 * Operation to automatically crop stacked images.
 * Removes edge artifacts from registration/integration.
 * Determines optimal crop region across frame sets.
 */
StackEngine.prototype.AutoCropOperation = class extends BPPOperationBlock
{
   constructor()
   {
      super( "Autocrop", undefined, true /* trackable */ );

   this.spaceRequired = () =>
   {
      // in the average case, we expect the cropped version to have a slightly smaller size than the original file.
      // We assume 95 % as the heuristic factor.
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => !g.isHidden );
      return groups.reduce( ( a, g ) =>
      {
         let size = g.frameSize();
         if ( g.isDrizzleEnabled() )
            size += g.drizzledFrameSize();
         return a + size;
      }, 0 );
   };

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Autocrop",
      status: this.status,
      statusMessage: this.statusMessage
   } );

   this._run = function( environment )
   {

      let totalToCrop = 0;
      let nSuccess = 0;
      let nCached = 0;
      let nFailed = 0;

      let allPostGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive );
      console.writeln( "Autocrop: active groups to be processed = ", allPostGroups.length );

      // we collect groups that shares the same reference frame. For each reference frame, all
      // groups will be cropped on the same region
      let refGroupsMap = allPostGroups.reduce( ( a, g ) =>
      {
         // we ignore the recombined rgb channels group
         if ( g.__reference_frame__ != undefined )
         {
            if ( g.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
            {
               if ( a[ g.__reference_frame__ ] == undefined )
                  a[ g.__reference_frame__ ] = [];
               a[ g.__reference_frame__ ].push( g );
            }
         }
         else
         {
            console.writeln( "Autocrop: group has no reference frame: ", g.toShortString() );
         }
         return a;
      },
      {} );
      let refFrames = Object.keys( refGroupsMap );
      console.writeln( "Autocrop: reference frames = ", refFrames.length );

      // the categories of master files to be cropped are
      // 1. ImageIntegration master files
      // 2. DrizzleIntegration master files
      // for each category a list of cropping groups are crated, in each cropping group all masters
      // shares the same reference frame
      let croppingGroups = [];

      // add the image integration masters files. We pick the master files names from the environment as they have to be
      // created by the execution of ImageIntegration first in the pipeline.
      // If ImageIntegration did fail, the group may remain active but no master file name is stored into the environment,
      // in that case we need to filter out these groups.
      [
      {
         desc: "image integration master light",
         isDrizzle: false
      },
      {
         desc: "drizzle master light",
         isDrizzle: true
      } ].forEach( item =>
      {
         refFrames.forEach( referenceFrame =>
         {
            let groups = refGroupsMap[ referenceFrame ];
            let filteredGroups = [];

            // we first filter the groups that has a valid master file name assocaited for both
            // master lights and drizzled master lights.
            groups.forEach( g =>
            {
               if ( !item.isDrizzle || ( item.isDrizzle && g.isDrizzleEnabled() ) )
               {
                  if ( g.getMasterFileName( item.isDrizzle ? BPP.MasterType.DRIZZLE : BPP.MasterType.MASTER_LIGHT ) != undefined )
                     filteredGroups.push( g );
                  else
                     console.warningln( "** Warning: Autocrop: ", item.desc, " not available for group ", g.toShortString() );
               }
            } );

            if ( filteredGroups.length > 0 )
            {

               let type = item.isDrizzle ? BPP.MasterType.DRIZZLE : BPP.MasterType.MASTER_LIGHT;
               let filePaths = filteredGroups.map( g => ( g.getMasterFileName( type ) ) );
               totalToCrop += filteredGroups.length;
               croppingGroups.push(
               {
                  groups: filteredGroups,
                  filePaths: filePaths,
                  referenceFrame: referenceFrame,
                  isDrizzle: item.isDrizzle
               } );
            }
         } );
      } );
      croppingGroups = croppingGroups.filter( cg => cg.groups.length > 0 );

      // log the crop groups
      croppingGroups.forEach( ( cg ) =>
      {
         console.noteln( "Autocrop: masters group for reference frame ", File.extractNameAndExtension( cg.referenceFrame ) );
         cg.filePaths.forEach( ( f, j ) =>
         {
            console.noteln( "Autocrop:     ", j, ". ", File.extractNameAndExtension( f ) );
         } );
      } );

      console.writeln( "Autocrop: the active crop groups count is ", croppingGroups.length );

      // loop through all aggregated groups and
      //    determine the common crop region
      //    crop all frames in the same group using the common crop region
      for ( let i = 0; i < croppingGroups.length; ++i )
      {
         let groups = croppingGroups[ i ].groups;
         let filePaths = croppingGroups[ i ].filePaths;
         let referenceFrame = croppingGroups[ i ].referenceFrame;
         let isDrizzle = croppingGroups[ i ].isDrizzle;

         console.writeln();
         console.writeln( "Autocrop: ---------------------------------------------" );
         console.writeln( "Autocrop: crop group ", i );
         console.writeln( "Autocrop: crop the following masters on reference frame: <raw>" + referenceFrame + "</raw>" );
         filePaths.forEach( f =>
         {
            console.writeln( "Autocrop: <raw>" + f + "</raw>" );
         } )
         console.writeln( "Autocrop: ---------------------------------------------" );
         console.writeln();

         // we check if the reference frame has already been cropped, if this is the case then
         // no crop needs to be applied.
         // This is the case where we selected an already cropped frame as reference frame; when this
         // happens the aligned frame already has the same frame size of the reference frame.
         let isAutocrop = WBPPUtils.keywords.readFileKeyword( referenceFrame, BPP.Keywords.AUTOCROP );
         if ( isAutocrop )
         {
            nSuccess += groups.length;
            console.writeln( "Autocrop: reference frame has already been cropped by WBPP; skip the cropping." );
            engine.processLogger.addMessage( "reference frame " + referenceFrame + " has already been cropped by WBPP; skip cropping " + filePaths.length + " master" + ( filePaths.length == 1 ? "" : "s" ) + " using it as the reference." );
            continue;
         }

         // check if cache exists
         // the cache key is generated from the concatenated sorted list of masters to be cropped
         let ACcacheKey = engine.executionCache.keyFor( filePaths.join( "|" ) );
         let ACCache = {
            previouslyFailed: false,
            cropRects:
            {}
         };
         let inputDataIsUnchanged = true;
         let outputDataIsUnchanged = true;

         // cache handling
         // we skip processing the whole grop if
         // - input files are unchanged
         // - the previous execution failed, so we already know that re-executing the autocrop will fail again
         // - the previous execution did not fail and the output files are unchanged
         if ( engine.executionCache.hasCacheForKey( ACcacheKey ) )
         {
            ACCache = engine.executionCache.cacheForKey( ACcacheKey );
            if ( ACCache.cropRects == undefined )
            {
               console.noteln( "Autocrop: missing crop rectangles cached data. Reprocess the master files." );
               ACCache.cropRects = {};
            }
            else
            {
               console.noteln( "Autocrop: has cached data for the key ", ACcacheKey );
               console.noteln( "Autocrop: check input files " );
               // all input files must be unchanged
               for ( let j = 0; inputDataIsUnchanged && j < filePaths.length; ++j )
               {
                  inputDataIsUnchanged = engine.executionCache.isFileUnmodified( ACcacheKey, filePaths[ j ] );
                  if ( !inputDataIsUnchanged )
                  {
                     console.noteln( "Autocrop: file has changed since last autocrop execution, ", filePaths[ j ] );
                     break;
                  }
                  else
                     console.noteln( "Autocrop: file is unmodified since last autocrop execution, ", filePaths[ j ] );
               }

               if ( inputDataIsUnchanged && ACCache.previouslyFailed )
               {
                  console.noteln( "Autocrop: input data is unchanged but the previous execution failed. Autocrop will be skipped." );
                  nFailed += groups.length;
                  continue;
               }
               else if ( inputDataIsUnchanged && !ACCache.previouslyFailed )
               {
                  console.noteln( "Autocrop: check output files " );
                  for ( let j = 0; outputDataIsUnchanged && j < filePaths.length; ++j )
                  {
                     let croppedFilePath = File.appendToName( filePaths[ j ], "_autocrop" );
                     outputDataIsUnchanged = engine.executionCache.isFileUnmodified( ACcacheKey, croppedFilePath );
                     if ( !outputDataIsUnchanged )
                     {
                        console.noteln( "Autocrop: file has changed since last autocrop execution, ", filePaths[ j ] );
                        break;
                     }
                     else
                        console.noteln( "Autocrop: file is unmodified since last autocrop execution, ", filePaths[ j ] );
                  }
               }

               // if data is unchanged if input files are unchanged and the previous execution failed or did not failed and output files are unchanged
               if ( inputDataIsUnchanged && outputDataIsUnchanged )
               {
                  // we have cached data with unchanged inputs and outputs that succeded in the previous execution.
                  // skip any opration and inject into the environment the crop rects to feed the drizzle integration in case.
                  let validCache = true;
                  let groupIDs = Object.keys( ACCache.cropRects );
                  groupIDs.forEach( key =>
                  {
                     let rect = ACCache.cropRects[ key ];
                     if ( rect != undefined )
                        try
                        {
                           environment[ key ] = new Rect( rect.x0, rect.y0, rect.x1, rect.y1 );
                        }
                     catch ( e )
                     {
                        validCache = false;
                     }
                     else
                        validCache = false;
                  } );
                  if ( !validCache )
                  {
                     console.noteln( "Autocrop: invalid crop rectangles cached data. Reprocess the master files." );
                  }
                  else
                  {
                     // set the autocrop master file into the groups
                     for ( let j = 0; j < groups.length; ++j )
                     {
                        let croppedFilePath = File.appendToName( filePaths[ j ], "_autocrop" );
                        groups[ j ].setMasterFileName( croppedFilePath, isDrizzle ? BPP.MasterType.DRIZZLE : BPP.MasterType.MASTER_LIGHT, BPP.MasterVariant.CROPPED );
                        engine.processLogger.addSuccess( "Autocrop: cached master", croppedFilePath );
                     }
                     console.noteln( "Autocrop: successfully cached cropped file found. Autocrop will be skipped." );
                     nCached += groups.length;
                     continue;
                  }
               }
            }
         }

         // detect the crop region for all masters first, then the unique crop
         // region applied to all of them will be the intersection of all individual crop regions
         let cropRectangles = [];
         for ( let j = 0; j < groups.length; ++j )
         {
            let masterFilePath = croppingGroups[ i ].filePaths[ j ];

            // cache the LMD for all input filepaths
            engine.executionCache.cacheFileLMD( ACcacheKey, masterFilePath );
            let result = {
               success: false
            };

            let group = groups[ j ];
            console.writeln( "Autocrop: process master: <raw>" + masterFilePath + "</raw>" );
            if ( isDrizzle )
            {
               // each group that is drizzled must have been processed once already to crop
               // the master light, so the crop region is available in the environment
               let cropRect = environment[ "crop_region_" + group.id ];
               if ( cropRect != undefined )
               {
                  let scale = group.drizzleScale();
                  cropRect.x0 = cropRect.x0 * scale;
                  cropRect.y0 = cropRect.y0 * scale;
                  cropRect.x1 = cropRect.x1 * scale;
                  cropRect.y1 = cropRect.y1 * scale;
                  result = {
                     success: true,
                     rect: cropRect
                  };
               }
               else
               {
                  console.warningln( "** Warning: Autocrop: crop region not found for drizzle master ", group.toString() );
               }
            }
            else
            {
               // open the master light and compute the crop region
               result = engine.imageProcessor.getAutocropRegion( masterFilePath, true /* returnTheWorkingImages */ );
               if ( !result.success )
               {
                  console.warningln( result.message );
                  engine.processLogger.addError( result.message );
                  console.warningln( "** Warning: Autocrop: failed to determine the crop region for file: <raw>" + masterFilePath + "</raw>" );
               }
               else
               {
                  let id = "crop_region_" + group.id;
                  environment[ id ] = result.rect;
                  ACCache.cropRects[ id ] = {
                     x0: result.rect.x0,
                     x1: result.rect.x1,
                     y0: result.rect.y0,
                     y1: result.rect.y1
                  };
               }
            }
            cropRectangles.push( result );
         }

         // report the result
         for ( let j = 0; j < groups.length; ++j )
         {
            let masterFilePath = filePaths[ j ];
            if ( cropRectangles[ j ].success )
            {
               let cropRect = cropRectangles[ j ].rect;
               let rectString = "(" + cropRect.x0 + "," + cropRect.y0 + "), (" + cropRect.x1 + "," + cropRect.y1 + ")";
               console.noteln( "* Autocrop: crop region ", rectString, " successflly computed for file: <raw>" + masterFilePath + "</raw>" );
            }
            else
            {
               console.warningln( "** Warning: Autocrop: failed to compute crop region for file: <raw>" + masterFilePath + "</raw>" );
               engine.processLogger.addWarning( "Failed to compute crop region for the file " + masterFilePath );
            }
         }

         // -------------------------------------------------
         // ensure that at least one crop region is available
         let oneOreMoreCropRegionsAvailable = false;
         for ( let j = 0; j < cropRectangles.length; ++j )
            if ( cropRectangles[ j ].success )
            {
               oneOreMoreCropRegionsAvailable = true;
               break;
            }

         if ( !oneOreMoreCropRegionsAvailable )
         {
            nFailed += groups.length;
            // update the cache
            ACCache.previouslyFailed = true;
            engine.executionCache.setCache( ACcacheKey, ACCache );
            // log
            let msg = "No autocrop regions defined. Autocrop will be skipped for master frames "
               + "aligned on reference frame " + referenceFrame;
            console.warningln( "** Warning: Autocrop: " + msg );
            engine.processLogger.addError( msg );
            continue;
         }

         // -------------------------------------------------
         // the final crop recion is computed as the intersection of all crop regions
         let cropRect = new Rect( -1, -1, 1e6, 1e6 );
         for ( let j = 0; j < cropRectangles.length; ++j )
         {
            if ( !cropRectangles[ j ].success )
               continue;
            let c = cropRectangles[ j ].rect;
            cropRect.intersect( new Rect( c.x0, c.y0, c.x1, c.y1 ) );
         }
         let rectString = "(" + cropRect.x0 + "," + cropRect.y0 + "), (" + cropRect.x1 + "," + cropRect.y1 + ")";
         console.noteln( "Autocrop: the applied crop region is ", rectString );

         // check the intersection result
         if ( cropRect.width == 0 || cropRect.height == 0 )
         {
            nFailed += groups.length;
            // update the cache
            ACCache.previouslyFailed = true;
            engine.executionCache.setCache( ACcacheKey, ACCache );
            // log
            console.warningln( "** Warning: Autocrop: crop region has null size " + cropRect.width + "x" + cropRect.height + "; crop will be skipped." );
            engine.processLogger.addError( "Crop region has null size " + cropRect.width + "x" + cropRect.height + "; crop will be skipped for master " + masterFilePath );
            continue;
         }

         // -------------------------------------------------
         // now we need to apply the crop to all master frames
         for ( let j = 0; j < groups.length; ++j )
         {
            let masterFilePath = filePaths[ j ];
            let croppedFilePath = File.appendToName( masterFilePath, "_autocrop" );

            console.writeln( "Autocrop: cropping file: <raw>" + masterFilePath + "</raw>" );

            let windows = ImageWindow.open( masterFilePath );
            if ( windows == undefined || windows.length == 0 )
            {
               console.warningln( "** Warning: Autocrop: failed to open master file: <raw>" + masterFilePath + "</raw>" );
               engine.processLogger.addError( "Failed to open master file: " + masterFilePath );
               nFailed++;
               continue;
            }
            let window = windows[ 0 ];
            // close the rejection maps
            let k = 1;
            while ( k < windows.length )
            {
               windows[ k ].forceClose();
               k++;
            }
            windows = [ window ];

            console.writeln( "Autocrop: generating the crop region image." );
            // generate the cropping mask
            let pm = new PixelMath;
            pm.expression = "iif("
               + "(x()==" + cropRect.x0 + " && y()>=" + cropRect.y0 + " && y()<=" + cropRect.y1 + ") || "
               + "(x()==" + cropRect.x1 + " && y()>=" + cropRect.y0 + " && y()<=" + cropRect.y1 + ") || "
               + "(y()==" + cropRect.y0 + " && x()>=" + cropRect.x0 + " && x()<=" + cropRect.x1 + ") || "
               + "(y()==" + cropRect.y1 + " && x()>=" + cropRect.x0 + " && x()<=" + cropRect.x1 + ")"
               + ",1,0)";
            pm.createNewImage = true;
            pm.showNewImage = false;
            pm.newImageId = "crop_mask";
            pm.newImageColorSpace = PixelMath.Gray;
            pm.newImageSampleFormat = PixelMath.i8;
            pm.executeOn( window.mainView );
            let maskImage = ImageWindow.windowById( "crop_mask" );

            // crop the image
            window.mainView.beginProcess();
            window.mainView.image.cropTo( cropRect );
            window.mainView.endProcess();

            // append the crop mask to the set of images stored into the XISF file
            windows.push( maskImage );

            window.keywords = window.keywords.concat(
               new FITSKeyword(
                  BPP.Keywords.AUTOCROP,
                  format( "(%d,%d)x(%d,%d)", cropRect.x0, cropRect.y0, cropRect.x1, cropRect.y1 ),
                  "WBPP Autocrop" )
            );

            engine.imageProcessor.writeImage(
               croppedFilePath,
               windows,
               [ "integration_autocrop",
                  "crop_mask"
               ] );

            // store the autocrop file name into the environment
            groups[ j ].setMasterFileName( croppedFilePath, isDrizzle ? BPP.MasterType.DRIZZLE : BPP.MasterType.MASTER_LIGHT, BPP.MasterVariant.CROPPED );

            windows.forEach( win =>
            {
               if ( win )
                  win.forceClose();
            } );
            console.noteln( "Autocrop: cropped master file saved at ", croppedFilePath );
            engine.processLogger.addSuccess( "Autocrop: cropped master file saved at", croppedFilePath );
            engine.executionCache.cacheFileLMD( ACcacheKey, croppedFilePath );
            nSuccess++;
         }

         // update the cache
         ACCache.previouslyFailed = false;
         engine.executionCache.setCache( ACcacheKey, ACCache );
      }

      engine.processLogger.addSuccess( "Autocrop completed", totalToCrop + " master file" + ( totalToCrop > 1 ? "s" : "" ) + " processed, " + ( nSuccess + nCached ) + " cropped." );
      this.statusMessage = WBPPUtils.resultCountToString( nCached, nSuccess, nFailed, "cropped" );
      if ( this.statusMessage == "" && nSuccess > 0 )
         this.statusMessage = nSuccess + " cropped";
      this.hasWarnings = nFailed > 0;
      if ( totalToCrop > 0 && nFailed == totalToCrop )
         return OperationBlockStatus.FAILED;
      else
         return OperationBlockStatus.DONE;
   }
   }
};

/**
 * Operation to recombine separate RGB channels.
 * Handles both regular and drizzle-integrated channels.
 */
StackEngine.prototype.RGBRecombinationOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "RGB Combination", frameGroup, true /* trackable */ );

   this.spaceRequired = () =>
   {
      // the group size if autocrop is not ebabled, otherwise both the uncropped and cropped files
      // will be recombined
      return frameGroup.frameSize() * ( engine.autocrop ? 2 : 1 );
   };
   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "RGB Combination",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      // get the recombined parent group, the R, G and B associated groups must have the same parent
      let parentGroupID = frameGroup.linkedGroupID;
      let singleChannelGroups = engine.getLinkedGroups( parentGroupID, frameGroup );

      if ( singleChannelGroups.length != 3 )
      {
         // something is wrong, the number of associated channels must be 3 at this point
         this.statusMessage = "Number of assocaited channels is " + singleChannelGroups.length + ", expected 3.";
         this.hasWarnings = true;
         return OperationBlockStatus.FAILED;
      }

      // check if drizzle is enabled for the first group, this means that it should be enabled for all groups and we have to
      // recombine the drizzle channels too
      let recombineDrizzle = singleChannelGroups[ 0 ].isDrizzleEnabled();
      let drizzlePostfix = "_" + singleChannelGroups[ 0 ].drizzleScale() + "x";

      // construct the list of master variants to recombined.
      let types = [
      {
         type: BPP.MasterType.MASTER_LIGHT,
         variant: BPP.MasterVariant.REGULAR,
         postfix: ""
      } ];

      if ( recombineDrizzle )
      {
         types.push(
         {
            type: BPP.MasterType.DRIZZLE,
            variant: BPP.MasterVariant.REGULAR,
            postfix: "_drizzle" + drizzlePostfix
         } );
      }

      if ( engine.autocrop )
      {
         types.push(
         {
            type: BPP.MasterType.MASTER_LIGHT,
            variant: BPP.MasterVariant.CROPPED,
            postfix: "_autocrop"
         } );
         if ( recombineDrizzle )
         {
            types.push(
            {
               type: BPP.MasterType.DRIZZLE,
               variant: BPP.MasterVariant.CROPPED,
               postfix: "_autocrop_drizzle" + drizzlePostfix
            } );
         }
      }

      let nSuccess = 0;
      let nFailed = 0;
      let nCached = 0;
      for ( let i = 0; i < types.length; ++i )
      {
         let type = types[ i ].type;
         let variant = types[ i ].variant;
         let postfix = types[ i ].postfix;

         // exctract the linkned groups ensuring that the correspondend master file is generated
         let linkedGroups = singleChannelGroups.reduce( ( acc, group ) =>
         {
            let filePath = group.getMasterFileName( type, variant );
            if ( filePath != undefined )
            {
               // store the file name that has been found in the environment associated to the group ID
               acc[ group.associatedRGBchannel ] = filePath;
            }
            return acc;
         },
         {} );

         if ( Object.keys( linkedGroups ).length < 3 )
         {
            let missingChannels = [ BPP.AssociatedChannel.R,
               BPP.AssociatedChannel.G,
               BPP.AssociatedChannel.B
            ].reduce( ( acc, ch ) =>
            {
               if ( linkedGroups[ ch ] == undefined )
                  acc.push( ch );
               return acc;
            }, [] );

            let message = "RGB combination not possible, " + postfix + " channel"
               + ( missingChannels.length > 1 ? "s " : " " ) + missingChannels.join( ", " ) + " not found.";
            console.warningln( "** Warning: " + message );
            engine.processLogger.addError( message );
            this.statusMessage = "missing " + missingChannels.join( ", " );
            nFailed++;
            continue;
         }

         // combine the channels
         let recombinedFileName = "master" + frameGroup.folderName().replace( " ", "_" ) + postfix + ".xisf";
         let
         {
            success,
            error,
            filePath,
            cached
         } = engine.imageProcessor.combineRGB(
            linkedGroups[ BPP.AssociatedChannel.R ],
            linkedGroups[ BPP.AssociatedChannel.G ],
            linkedGroups[ BPP.AssociatedChannel.B ],
            recombinedFileName );

         // check the result
         if ( !success )
         {
            console.warningln( "** Warning: " + error );
            engine.processLogger.addError( "Warning: " + error );
            this.statusMessage = "combined RGB file not generated";
            nFailed++;
            continue;
         }

         // success
         frameGroup.setMasterFileName( filePath, type, variant );
         if ( cached )
            nCached++;
         else
            nSuccess++;

         engine.processLogger.addSuccess( "RGB Combination completed", "combined file saved at path " + filePath );
      };

      // done
      this.statusMessage = WBPPUtils.resultCountToString( nCached, nSuccess, nFailed, "recombined" );
      this.hasWarnings = nFailed > 0;
      return nCached + nSuccess > 0 ? OperationBlockStatus.DONE : OperationBlockStatus.FAILED;
   };
   }
};

/**
 * Operation to compute astrometric solution for images.
 * Handles both regular and drizzle-integrated masters.
 */
StackEngine.prototype.PlateSolveOperation = class extends BPPOperationBlock
{
   constructor( frameGroup )
   {
      super( "Astrometric solution", frameGroup, true /* trackable */ );

   this.spaceRequired = () => 0;

   /**
    * Standard group data for the event script
    *
    */
   this.envForScript = () => (
   {
      name: "Astrometric solution",
      status: this.status,
      statusMessage: this.statusMessage,
      group: frameGroup
   } );

   this._run = function()
   {
      // the first requirement is that a regular master light has been successfully generated
      let masterLightFileName = frameGroup.getMasterFileName( BPP.MasterType.MASTER_LIGHT, BPP.MasterVariant.REGULAR );
      if ( masterLightFileName == undefined || !File.exists( masterLightFileName ) )
      {
         console.warningln( "** Warning: No master file found for group ", frameGroup.toShortString() );
         engine.processLogger.addError( "Warning: No master file generated." );
         this.statusMessage = "no master file generated";
         return OperationBlockStatus.CANCELED;
      }

      // list the masters to integrate, masters is an array of objects with the following properties:
      // fName: the file name of the master
      // type: the type of the master
      let masters = [];
      for ( let type = 0; type < BPP.MasterType.NOptions; ++type )
         for ( let variant = 0; variant < BPP.MasterVariant.NOptions; ++variant )
         {
            // push the master file name if it exists
            let fName = frameGroup.getMasterFileName( type, variant );
            if ( fName != undefined && File.exists( fName ) )
               masters.push(
               {
                  fName: fName,
                  type: type
               } );
         }

      // reuse the reference frame's metadata if available
      let metadata = undefined;

      // extract the cache center coordinates and pixel scale for the reference frame
      let AScacheKey = engine.executionCache.keyFor( "astrometry_" + frameGroup.__reference_frame__ );
      if ( engine.executionCache.hasCacheForKey( AScacheKey ) )
      {
         // extract the center coordinates
         metadata = engine.executionCache.cacheForKey( AScacheKey );
      }

      let nCached = 0;
      let nSuccess = 0;
      let nFailed = 0;

      // find the masters to solve, skipping the cached ones
      let mastersToSolve = masters.reduce( ( acc, masterInfo ) =>
      {
         if ( engine.executionCache.isFileUnmodified( AScacheKey, masterInfo.fName ) )
            nCached++;
         else
            acc.push( masterInfo );
         return acc;
      }, [] );

      // solve each master
      for ( let i = 0; i < mastersToSolve.length; ++i )
      {
         let masterData = mastersToSolve[ i ];
         console.writeln( "Compute the astrometric solution for file: <raw>" + masterData.fName + "</raw>" );
         let windows = ImageWindow.open( masterData.fName );
         if ( windows.length > 0 )
         {
            let window = windows[ 0 ];
            try
            {
               let imageMetadata = {};
               // prepare the metadata, if available
               if ( metadata != undefined )
               {
                  imageMetadata.startTime = metadata.startTime;
                  imageMetadata.observationTime = metadata.observationTime;
                  imageMetadata.ra = metadata.ra;
                  imageMetadata.dec = metadata.dec;
                  let dzScale = ( masterData.type == BPP.MasterType.DRIZZLE ) ? frameGroup.drizzleScale() : 1;
                  // if the group is associated to a combined RGB group, use the drizzle scale of the first associated group
                  if ( masterData.type == BPP.MasterType.DRIZZLE && frameGroup.associatedRGBchannel == BPP.AssociatedChannel.COMBINED_RGB && frameGroup.linkedGroupID != undefined )
                  {
                     let associatedGroups = engine.getLinkedGroups( frameGroup.linkedGroupID, frameGroup );
                     if ( associatedGroups.length == 3 )
                        dzScale = associatedGroups[ 0 ].drizzleScale();
                  }
                  imageMetadata.resolution = metadata.resolution / dzScale;
                  imageMetadata.xpixsz = metadata.xpixsz / dzScale;
                  imageMetadata.useFocal = false;
                  console.writeln( format( "* Using cached metadata: ra=%.8f deg dec=%+.8f deg xpixsz=%.2f um (scale=%d:1)",
                     imageMetadata.ra, imageMetadata.dec, imageMetadata.xpixsz, dzScale ) );
               }
               // solve the image
               let solver = engine.plateSolver.solveImage( window,
               {}, imageMetadata );
               if ( solver != undefined )
               {
                  // save the metadata in cache
                  if ( metadata == undefined )
                  {
                     metadata = {
                        startTime: solver.metadata.startTime,
                        observationTime: solver.metadata.observationTime,
                        ra: solver.metadata.ra,
                        dec: solver.metadata.dec,
                        resolution: solver.metadata.resolution,
                        xpixsz: solver.metadata.xpixsz
                     };
                     engine.executionCache.setCache( AScacheKey, metadata );
                  }
                  // update the last modified date
                  let previousLMD = WBPPUtils.getLastModifiedDate( masterData.fName );
                  engine.imageProcessor.writeImage( masterData.fName, windows, windows.map( w => w.originalImageId ) );
                  let newLMD = WBPPUtils.getLastModifiedDate( masterData.fName );
                  engine.executionCache.cacheFileLMD( AScacheKey, masterData.fName );
                  engine.executionCache.updateLMD( masterData.fName, previousLMD, newLMD );
                  nSuccess++;
                  engine.processLogger.addSuccess( "Astrometric solution completed", masterData.fName );
               }
               else
               {
                  console.warningln( "** Warning: Astrometric solution failed: <raw>" + masterData.fName + "</raw>" );
                  nFailed++;
               }
            }
            catch ( e )
            {
               console.warningln( "** Warning: Astrometric solution failed: <raw>" + masterData.fName + "</raw> with error ", e );
               nFailed++;
            }
            window.forceClose();
         }
         else
         {
            console.warningln( "** Warning: No images found in master file: <raw>" + masterData.fName + "</raw>" );
            nFailed++;
            continue;
         }
      }

      // done
      this.statusMessage = WBPPUtils.resultCountToString( nCached, nSuccess, nFailed, "solved" );
      this.hasWarnings = nFailed > 0;
      return ( nCached + nSuccess > 0 ) ? OperationBlockStatus.DONE : OperationBlockStatus.FAILED;
   }
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-Operations.js - Released 2026-05-10T11:05:00Z
