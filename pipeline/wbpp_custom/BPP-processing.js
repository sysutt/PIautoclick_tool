// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Processing.js - Released 2026-05-10T11:05:00Z
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

#include <pjsr/process/LinearDefectDetection.js>
#include <pjsr/process/LinearPatternSubtraction.js>

// ----------------------------------------------------------------------------

var ImageProcessor = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   // ........................................................................

   /**
    * Returns the FITS coordinate convention hints given the current global option status
    *
    * @return {*}
    */
   coordinateConventionHints()
   {
      let engine = this.engine;
      if ( engine.fitsCoordinateConvention != 0 )
         return ( engine.fitsCoordinateConvention == 1 ) ? " up-bottom" : " bottom-up";
      return "";
   }

   /**
    * Returns the input hits to keep the white balance convention if the global setting is set
    * to do so.
    */
   whiteBalanceHints()
   {
      let engine = this.engine;
      if ( engine.preserveWhiteBalance )
         return " camera-white-balance";
      return "";
   }

   /**
    * Provides default input file hints.
    *
    * @returns
    */
   inputHints()
   {
      // Input format hints:
      // * XISF: fits-keywords normalize only-first-image
      // * FITS: only-first-image signed-is-physical use-roworder-keywords up-bottom|bottom-up
      // * DSLR_RAW: raw cfa
      return "fits-keywords normalize only-first-image raw cfa use-roworder-keywords signed-is-physical" + this.coordinateConventionHints() + this.whiteBalanceHints();
   }

   // ........................................................................

   /**
    * Provides default output file hints.
    *
    * @returns
    */
   outputHints()
   {
      // Output format hints:
      // * XISF: properties fits-keywords no-compress-data block-alignment 4096 max-inline-block-size 3072 no-embedded-data no-resolution
      // * FITS: up-bottom|bottom-up

      return "properties fits-keywords no-compress-data block-alignment 4096 max-inline-block-size 3072 no-embedded-data no-resolution "
         + this.coordinateConventionHints();
   }

   // ........................................................................

   /**
    * Opens the image at filePath and returns the generated Window object.
    *
    * @param {String} filePath
    * @returns
    */
   readImage( filePath )
   {
      let ext = File.extractExtension( filePath );
      let F = new FileFormat( ext, true /*toRead*/ , false /*toWrite*/ );
      if ( F.isNull )
         throw new Error( "No installed file format can read \'" + ext + "\' files." ); // shouldn't happen

      let f = new FileFormatInstance( F );
      if ( f.isNull )
         throw new Error( "Unable to instantiate file format: " + F.name );

      let d = f.open( filePath, this.inputHints() );
      if ( d.length < 1 )
         throw new Error( "Unable to open file: " + filePath );
      if ( d.length > 1 )
         throw new Error( "Multi-image files are not supported by this script: " + filePath );

      let window = new ImageWindow( 1, 1, 1, /*numberOfChannels*/ 32, /*bitsPerSample*/ true /*floatSample*/ );

      let view = window.mainView;
      view.beginProcess( UndoFlag.NoSwapFile );

      if ( !f.readImage( view.image ) )
         throw new Error( "Unable to read file: " + filePath );

      if ( F.canStoreImageProperties )
         if ( F.supportsViewProperties )
         {
            let info = view.importProperties( f );
            if ( !WBPPUtils.isEmptyString( info ) )
               console.criticalln( "<end><cbr>*** Error reading image properties:<br>" + info );
         }

      if ( F.canStoreKeywords )
         window.keywords = f.keywords;

      view.endProcess();

      f.close();

      return window;
   }

   // ........................................................................

   /**
    * Writes an image to file.
    *
    * @param {String} filePath
    * @param {[ImageWindow]} imageWindows an array of image windows
    * @param {[String]} identifiers an optional array of identifiers
    * @param {[String]} imageHistory an optional string of XML source code representation of the image history
    */
   writeImage( filePath, imageWindows, identifiers, imageHistory )
   {
      if ( imageWindows.length == 0 )
      {
         console.critical( "*** Internal Error: ImageProcessor.writeImage(): Empty image array provided. "
                                             + "No image will be saved: <raw>" + filePath + "</raw>" );
         return;
      }
      if ( imageWindows.length != identifiers.length )
      {
         console.critical( "*** Internal Error: ImageProcessor.writeImage(): The number of images and identifiers must match. "
                                             + "No image will be saved: <raw>" + filePath + "</raw>" );
         return;
      }

      let F = new FileFormat( ".xisf", false /*toRead*/ , true /*toWrite*/ );
      if ( F.isNull )
         throw new Error( "No installed file format can write .xisf files." ); // shouldn't happen

      let f = new FileFormatInstance( F );
      if ( f.isNull )
         throw new Error( "Unable to instantiate file format: " + F.name );

      if ( !f.create( filePath, this.outputHints() ) )
         throw new Error( "Error creating output file: " + filePath );

      let filename_id = imageIdFromFileName( File.extractName( filePath ) );

      for ( let i = 0; i < imageWindows.length; ++i )
         if ( imageWindows[i] !== null )
         {
            let d = new ImageDescription;
            d.bitsPerSample = imageWindows[i].bitsPerSample;
            d.ieeefpSampleFormat = imageWindows[i].isFloatSample;
            d.imageType = imageWindows[i].imageType;
            if ( !f.setOptions( d ) )
               throw new Error( "Unable to set output file options: " + filePath );

            f.keywords = imageWindows[i].keywords;

            imageWindows[i].mainView.exportProperties( f );

            let pc = imageWindows[i].mainView.initialProcessing;
            if ( pc.length > 0 )
            {
               let history = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><ProcessingHistory version=\"1.0\">";
               for ( let j = 0; j < pc.length; ++j )
                  history += pc[j].toSource( "XPSM 1.0" );
               history += "</ProcessingHistory>";
               f.writeImageProperty( "PixInsight:ProcessingHistory", history );
            }

            f.setImageId( identifiers[i].replace( filename_id, "" ) );

            if ( !f.writeImage( imageWindows[i].mainView.image ) )
               throw new Error( "Error writing output file: " + filePath );
         }

      f.close();
   }

   // ........................................................................

   setImagePropertyString( window, property, value )
   {
      let stringValue = ( value instanceof Date ) ? value.toISOString() : value;
      window.mainView.setPropertyValue( property, stringValue, PropertyType.IsoString, PropertyAttribute.Storable | PropertyAttribute.Permanent );
   }

   // ........................................................................

   generateSignatureProperty( window )
   {
      let engine = this.engine;
      window.mainView.setPropertyValue( "PCL:Signature:Preprocessing",
         "process=" + engine.id
         + ",version=" + engine.version
         + ",timestamp=" + ( new Date ).toISOString(),
         PropertyType.IsoString,
         PropertyAttribute.Storable | PropertyAttribute.Permanent );
   }

   // ........................................................................

   /**
    * Returns the auto crop region for an image.
    * The autocrop region is computed analyzing the low rejection map and the crop region represents the
    * the largest rectangle that includes pixels with low rejection values greather than 0.5.
    * The method assumes to find the low rejection map store in the image file, if this is not the case
    * it attempts to load the file with the postfix "_low_rejection". If none is found then no crop region
    * is computed.
    *
    * @param {*} filePath the file path of the image
    * @param {*} returnTheWorkingImages if TRUE, the main image window remains open once the function returns
    * @returns the Rect defining the crop region of the image, undefined in case of errors.
    */
   getAutocropRegion( filePath, returnTheWorkingImages )
   {
      if ( !File.exists( filePath ) )
         return {
            success: false,
            message: "unable to compute the autocrop region, file not found at path: " + filePath
         };

      let windows = ImageWindow.open( filePath );
      // ensure that data has been loaded
      if ( windows == undefined || windows.length == 0 )
         return {
            success: false,
            message: "unable to compute the autocrop region, file not loaded at path: " + filePath
         };

      // expect to find the main window and, optionally, the rejection high and low ones
      let mainWindow = windows[ 0 ];
      let rejLowWindow;
      let rejHighWindow;

      // Search for the low and high rejection maps within the loaded images.
      // N.B.: We must be robust to the current state of the "use filenames as
      // image identifiers" global preferences setting.
      for ( let i = 1; i < windows.length; ++i )
      {
         if ( windows[ i ].mainView.id.indexOf( "rejection_low" ) >= 0 )
            rejLowWindow = windows[ i ];
         if ( windows[ i ].mainView.id.indexOf( "rejection_high" ) >= 0 )
            rejHighWindow = windows[ i ];
      }

      // If rejection low is not present, the autocrop operation cannot continue.
      if ( rejLowWindow == undefined )
      {
         for ( let i = 0; i < windows.length; ++i )
            windows[ i ].forceClose();
         return {
            success: false,
            message: "unable to compute the autocrop region, low rejection map not found at path: " + filePath
         };
      }

      // compute the crop region
      let image = rejLowWindow.mainView.image;
      // memoization of the bottom and top Y coordinate available for each x coordinate
      let bottomY = new Array( image.width );
      let upperY = new Array( image.width );
      let rightX = new Array( image.height );
      let leftX = new Array( image.height );

      // crop coordinates
      let cx0 = 0;
      let cx1 = 0;
      let cy0 = 0;
      let cy1 = 0;

      // ROWS SCAN
      let maxArea = 0;
      let TOLERANCE = 0.25;

      for ( let row = 0; row < image.height; row++ )
      {
         // find the (x0,x1) extremes of the row
         let x0 = 0;
         while ( x0 < image.width && image.sample( x0, row ) > TOLERANCE )
            x0++;
         if ( x0 == image.width )
            continue;

         let x1 = image.width - 1;
         while ( image.sample( x1, row ) > TOLERANCE )
            x1--;

         // skip if the max possible area is lower than the current max
         if ( ( x1 - x0 ) * ( image.height - row ) <= maxArea && ( x1 - x0 ) * row <= maxArea )
            continue;

         // find the bottom Y values for each column (scan from bottom upward
         // through the full column so the cached value is always correct)
         let Ybottom = [ x0, x1 ].map( x =>
         {
            if ( bottomY[ x ] != undefined )
               return bottomY[ x ];
            let y = image.height - 1;
            while ( y >= 0 && image.sample( x, y ) > TOLERANCE )
               y--;
            bottomY[ x ] = y;
            return y;
         } );
         // the bottom Y coordinate is the lower one
         let yb = Math.min( Ybottom[ 0 ], Ybottom[ 1 ] );

         // find the top Y values for each column (scan from top downward
         // through the full column so the cached value is always correct)
         let Ytop = [ x0, x1 ].map( x =>
         {
            if ( upperY[ x ] != undefined )
               return upperY[ x ];
            let y = 0;
            while ( y < image.height && image.sample( x, y ) > TOLERANCE )
               y++;
            upperY[ x ] = y;
            return y;
         } );
         // the top Y coordinate is the higher one
         let yt = Math.max( Ytop[ 0 ], Ytop[ 1 ] );

         // check the bottom area
         let area = ( x1 - x0 ) * ( yb - row );
         if ( area > maxArea )
         {
            maxArea = area;
            cx0 = x0;
            cy0 = row;
            cx1 = x1;
            cy1 = yb;
         }
         // check the top area
         area = ( x1 - x0 ) * ( row - yt );
         if ( area > maxArea )
         {
            maxArea = area;
            cx0 = x0;
            cy0 = yt;
            cx1 = x1;
            cy1 = row;
         }
      }

      for ( let col = 0; col < image.width; col++ )
      {
         // find the (y0,y1) extremes of the column
         let y0 = 0;
         while ( y0 < image.height && image.sample( col, y0 ) > TOLERANCE )
            y0++;
         if ( y0 == image.height )
            continue;

         let y1 = image.height - 1;
         while ( image.sample( col, y1 ) > TOLERANCE )
            y1--;

         // skip if the max possible area is lower than the current max
         if ( ( y1 - y0 ) * ( image.width - col ) <= maxArea && ( y1 - y0 ) * col <= maxArea )
            continue;

         // find the right X values for each row (scan from right leftward
         // through the full row so the cached value is always correct)
         let Xright = [ y0, y1 ].map( y =>
         {
            if ( rightX[ y ] != undefined )
               return rightX[ y ];
            let x = image.width - 1;
            while ( x >= 0 && image.sample( x, y ) > TOLERANCE )
               x--;
            rightX[ y ] = x;
            return x;
         } );
         // the right X coordinate is the lower one
         let xr = Math.min( Xright[ 0 ], Xright[ 1 ] );

         // find the left X values for each row (scan from left rightward
         // through the full row so the cached value is always correct)
         let Xleft = [ y0, y1 ].map( y =>
         {
            if ( leftX[ y ] != undefined )
               return leftX[ y ];
            let x = 0;
            while ( x < image.width && image.sample( x, y ) > TOLERANCE )
               x++;
            leftX[ y ] = x;
            return x;
         } );
         // the left X coordinate is the higher one
         let xl = Math.max( Xleft[ 0 ], Xleft[ 1 ] );

         // check the bottom area
         let area = ( y1 - y0 ) * ( xr - col );
         if ( area > maxArea )
         {
            maxArea = area;
            cx0 = col;
            cy0 = y0;
            cx1 = xr;
            cy1 = y1;
         }
         // check the top area
         area = ( y1 - y0 ) * ( col - xl );
         if ( area > maxArea )
         {
            maxArea = area;
            cx0 = xl;
            cy0 = y0;
            cx1 = col;
            cy1 = y1;
         }
      }

      // build the returned object
      let retVal = {
         success: true,
         rect: new Rect( cx0, cy0, cx1, cy1 )
      };

      if ( returnTheWorkingImages )
      {
         retVal.mainWindow = mainWindow;
         retVal.rejLowWindow = rejLowWindow;
         retVal.rejHighWindow = rejHighWindow;
      }
      else
      {
         for ( let i = 0; i < windows.length; ++i )
            windows[ i ].forceClose();
      }
      return retVal;
   }

   // ........................................................................

   /**
    * Generates the local normalization reference frame and returns the file path.
    *
    * @param {*} group
    * @param {*} bestFrames
    * @param {*} logEnabled
    * @param {*} desiredFileName
    */
   generateLNReference( group, bestFrames, logEnabled, desiredFileName )
   {
      let engine = this.engine;
      let activeFrames = group.activeFrames();
      if ( logEnabled == undefined )
         logEnabled = true;

      let lbl = engine.subframeAnalyzer.readableLNReferenceSelectionMethod();
      let dk;

      if ( bestFrames == undefined )
      {
         let
         {
            descriptorKey,
            N,
            activeFrames
         } = engine.subframeAnalyzer.sortFramesForLocalNormalizationReference( group );
         dk = descriptorKey;
         bestFrames = activeFrames.slice( 0, N );
         console.noteln( "* Selecting the best reference frames for Local Normalization using ", dk, " metric." );
      }

      // if 1 frame hes been selected then return it, otherwise proceed with the integration
      if ( engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.SINGLE_BEST )
      {
         console.noteln( "* Local normalization: using the single best frame as reference." );
         if ( logEnabled )
            engine.processLogger.addSuccess( "Local normalization", "using the single frame with ", dk, " as reference." );
         return {
            lnReferenceFilePath: bestFrames[ 0 ].current,
            cached: false
         };
      }
      else if ( bestFrames.length < 3 )
      {
         console.warningln( "** Warning: Local normalization: not enough best frames found; using the single best frame as reference." );
         if ( logEnabled )
            engine.processLogger.addWarning( "Local normalization: ", "not enough best frames found; using the single best frame as reference." );
         return {
            lnReferenceFilePath: bestFrames[ 0 ].current,
            cached: false
         };
      }

      console.noteln( "Local normalization: generate the reference frame selecting " + bestFrames.length + " frames with " + lbl + " amongst " + activeFrames.length + " frames" );
      // do LN and Integration on a temporary group overriding the method to MEDIAN
      let integrationGroup = group.cloneWithActiveItems( bestFrames );

      // perform local normalization using the best frame as reference
      let integratedFrames = integrationGroup.activeFrames();
      let LN = new LocalNormalization;

      let subfolder = integrationGroup.folderName();
      LN.outputDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/registered/" + subfolder + "/ln_reference_frame_data" );

      // read the current reference frame size

      let referenceImageSize = WBPPUtils.getImageSize( integratedFrames[ 0 ].current );
      let imageRefrenceDimension = Math.min( referenceImageSize.width, referenceImageSize.height );

      LN.referencePathOrViewId = integratedFrames[ 0 ].current;
      LN.referenceIsView = false;
      LN.scale = imageRefrenceDimension / engine.localNormalizationGridSize;
      LN.referenceRejection = true;
      LN.referenceRejectionThreshold = 3.00;
      LN.targetRejectionThreshold = 3.20;
      LN.psfMaxStars = engine.localNormalizationPsfMaxStars;
      LN.psfMinSNR = engine.localNormalizationPsfMinSNR;
      LN.psfAllowClusteredSources = engine.localNormalizationPsfAllowClusteredSources;
      LN.lowClippingLevel = engine.localNormalizationLowClippingLevel;
      LN.highClippingLevel = engine.localNormalizationHighClippingLevel;
      LN.scaleEvaluationMethod = engine.localNormalizationMethod == 0
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
      LN.overwriteExistingFiles = false;

      let LNSource = LN.toSource( "JavaScript", "LN" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
      console.writeln( BPP.Format.SEPARATOR2 );
      console.writeln( LNSource );
      console.writeln( BPP.Format.SEPARATOR2 );

      // Check if valid cached data is present
      let fileItemsToNormalize = integratedFrames;
      let LNCache = {};
      let LNcacheKey = engine.executionCache.keyFor( "LNReference" + LNSource );
      if ( engine.executionCache.hasCacheForKey( LNcacheKey ) )
      {
         console.noteln( "LN Reference frame generation has cached data for key ", LNcacheKey );

         // the cache is the map between each input file and the correspondent output xnml file
         LNCache = engine.executionCache.cacheForKey( LNcacheKey );

         // check if the reference file is unchanged
         if ( engine.executionCache.isFileUnmodified( LNcacheKey, LN.referencePathOrViewId ) )
         {
            fileItemsToNormalize = [];
            // check which input file is unchanged
            for ( let i = 0; i < integratedFrames.length; ++i )
            {
               let inputFile = integratedFrames[ i ].current;
               let lnFile = LNCache[ inputFile ];
               if ( engine.executionCache.isFileUnmodified( LNcacheKey, inputFile )
                  && engine.executionCache.isFileUnmodified( LNcacheKey, lnFile ) )
               {
                  // the cached ln file is valid, associate it
                  integratedFrames[ i ].addLocalNormalizationFile( lnFile );
                  console.noteln( "LN file is cached: [", inputFile, "] -> [", lnFile, "]" );
               }
               else
               {
                  fileItemsToNormalize.push( integratedFrames[ i ] );
                  console.noteln( "LN file will be generated for: [", inputFile, "]" );
               }
            }
         }
      }
      else
      {
         console.noteln( "LN Reference frame generation has no cache data for key ", LNcacheKey );
      }

      let filePaths = fileItemsToNormalize.map( item => item.current );
      // process is saved in container with the full list of files to be normalized
      LN.targetItems = WBPPUtils.enableTargetFrames( filePaths, 2 );
      engine.processContainer.add( LN );
      engine.pipelineManager.flushProcessContainer();

      // perform LN if there are files to normalize
      let lnSuccess = true;
      if ( filePaths.length > 0 )
      {
         LN.targetItems = WBPPUtils.enableTargetFrames( filePaths, 2 );
         lnSuccess = LN.executeGlobal();
      }

      // ignore any result if something went wrong. We accept LN data only if normalized files have been gerenrated for
      // all input files provided
      let useLN = true;

      /* AUX: delete all normalized files generated by the provided LN instance */
      let cleanLNFiles = function( LN )
      {
         if ( !LN.outputData )
            return;

         let lnFiles = LN.outputData.map( item => ( item[ 0 ] || "" ) );
         for ( let k = 0; k < lnFiles.length; ++k )
            if ( lnFiles[ k ].length > 0 && File.exists( lnFiles[ k ] ) )
               File.remove( lnFiles[ k ] );
      }

      // clean the generated ln files and disable LN if something went wrong
      let lnFiles = [];
      if ( !lnSuccess )
         useLN = false;
      else if ( fileItemsToNormalize.length > 0 )
      {
         if ( !LN.outputData || LN.outputData.length != fileItemsToNormalize.length )
            useLN = false;
         else
         {
            lnFiles = LN.outputData.map( item => ( item[ 0 ] || "" ) );
            // ensure that LN files have been created for each file
            for ( let k = 0; k < lnFiles.length; ++k )
               if ( lnFiles[ k ].length == 0 || !File.exists( lnFiles[ k ] ) )
               {
                  useLN = false;
                  break;
               }
         }
      }

      // in case of success then integrate the input files along with the corresponding local normalization files
      if ( useLN )
      {
         // merge cached and generated normalized files
         for ( let i = 0; i < filePaths.length; ++i )
         {
            let inputFile = filePaths[ i ];
            let lnFile = lnFiles[ i ];
            fileItemsToNormalize[ i ].addLocalNormalizationFile( lnFile );
            console.noteln( "associate the local normalization file: [" + fileItemsToNormalize[ i ].current + "] -> [" + lnFile + "]" );

            // cache the result
            LNCache[ inputFile ] = lnFile;
            engine.executionCache.cacheFileLMD( LNcacheKey, inputFile );
            engine.executionCache.cacheFileLMD( LNcacheKey, lnFile );
            LNCache[ inputFile ] = lnFile;
         }
         // save the updated cache
         engine.executionCache.setCache( LNcacheKey, LNCache );

         // integrate the reference frame
         let
         {
            masterFilePath,
            cached
         } = this.doIntegrate(
            integrationGroup, /* frameGroup */
            "LN_Reference_", /* customPrefix */
            "", /* customPostfix */
            undefined, /* customGenerateRejectionMaps */
            false, /* customGenerateDrizzle */
            desiredFileName, /* desired master file name */
            {
               /* II overridden parameters */
               combination: ImageIntegration.Average,
               rejection: integrationGroup.bestRejectionMethod(),
               normalization: ImageIntegration.AdditiveWithScaling,
               rejectionNormalization: ImageIntegration.LocalRejectionNormalization,
               weightMode: ImageIntegration.PSFSignalWeight,
               rangeClipLow: true,
               rangeLow: 0,
               generateRejectionMaps: false,
               minWeight: 0
            },
            undefined /* FITS keywords */
         );

         // if integration failed then return the best frame
         if ( WBPPUtils.isEmptyString( masterFilePath ) )
         {
            console.warningln( "** Warning: Local normalization: integration failed; using the best frame as reference." );
            if ( logEnabled )
               engine.processLogger.addWarning( "Local normalization: ", "integration failed; using the best frame as reference." );
            return {
               lnReferenceFilePath: integratedFrames[ 0 ].current,
               cached: false
            };
         }
         console.noteln( "* Local normalization: reference frame generated by integrating " + integratedFrames.length + " frames." );
         if ( logEnabled )
            engine.processLogger.addSuccess( "Local normalization", "reference frame generated by integrating " + integratedFrames.length + " frames" );
         return {
            lnReferenceFilePath: masterFilePath,
            cached: cached
         };
      }
      else
      {
         cleanLNFiles( LN );
         console.warningln( "** Warning: Local normalization, local normalizaton of best frames failed; using the best frame as reference" );
         if ( logEnabled )
            engine.processLogger.addWarning( "Local normalization: ", "local normalizaton of best frames failed; using the best frame as reference" );
         return {
            lnReferenceFilePath: integratedFrames[ 0 ].current,
            cached: false
         };
      }
   }

   // ........................................................................

   /**
    * Integrates the provided group.
    *
    * @param {*} frameGroup
    * @param {String} customPrefix custom prefix to be added at the end of the master frame (default is "master")
    * @param {String} customPostfix custom postfix to be added at the end of the master frame
    * @param {Boolean} customGenerateRejectionMaps optionally overrides the rejection maps setting
    * @param {Boolean} customGenerateDrizzle optionally override the drizzle files generation
    * @param {String} desiredFileName optionally requires a master file name
    * @param {Boolean} overrideIIparameters to override ImageIntegration's parameters, needs to be an object with key/values
    * @param {Array} FITSKeywords optional list of FITS keyword to inject into the integrated image before saving
    *
    */
   doIntegrate( frameGroup,
      customPrefix,
      customPostfix,
      customGenerateRejectionMaps,
      customGenerateDrizzle,
      desiredFileName,
      overrideIIparameters,
      FITSKeywords )
   {
      let engine = this.engine;
      let filePath = "";
      let imageType = frameGroup.imageType;

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin integration of ", StackEngine.imageTypeToString( imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();

      let useCache = false;
      let numberOfImages = -1;
      let failedFrames = [];

      let activeFrames = frameGroup.activeFrames();
      if ( activeFrames.length < 3 )
      {
         console.warningln( "** Warning: Cannot integrate less than three frames." );
         engine.processLogger.addWarning( "Cannot integrate less than three frames." );
      }
      else
      {
         // Image Integration

         let selectedRejection = ( engine.rejection[ BPP.imageTypeIndex( imageType ) ] == BPP.REJECTION_AUTO )
            ? frameGroup.bestRejectionMethod() : engine.rejection[ BPP.imageTypeIndex( imageType ) ];

         if ( engine.rejection[ BPP.imageTypeIndex( imageType ) ] == BPP.REJECTION_AUTO )
         {
            console.noteln( "Rejection method auto-selected: ", engine.rejectionName( selectedRejection ) );
            engine.processLogger.addMessage( "<b>Rejection method auto-selected:</b> " + engine.rejectionName( selectedRejection ) );
         }
         else
         {
            console.noteln( "<b>Rejection method:</b> ", engine.rejectionName( selectedRejection ) );
         }

         // Drizzle is generated only for Light frames
         let generateDrizzle = imageType == ImageType.Light && ( ( customGenerateDrizzle != undefined ) ? customGenerateDrizzle : true );

         // ensure that drizzle files exists otherwise we disable the drizzle handling
         if ( imageType == ImageType.Light )
            for ( let i = 0; i < activeFrames.length; ++i )
            {
               let sanitizedFileName = activeFrames[ i ].drizzleFile || "";
               let valid = sanitizedFileName.length > 0;

               if ( !valid || !File.exists( sanitizedFileName ) )
               {
                  generateDrizzle = false;
                  console.warningln( "** Warning: Drizzle file not found: <raw>" + activeFrames[ i ].drizzleFile + "</raw>" );
                  console.warningln( "** Disabling the update of the drizzle files." );
                  break;
               }
            }

         // add local normalization files if xnml files are found for all frames
         let useLN = activeFrames.reduce( ( acc, item ) => ( acc && ( item.localNormalizationFile != undefined ) ), true );
         let embedRejectionMaps = ( customGenerateRejectionMaps != undefined ) ? customGenerateRejectionMaps : engine.generateRejectionMaps;

         let II = new ImageIntegration;
         II.inputHints = this.inputHints();
         II.overrideImageType = true;
         II.imageType = imageType; // N.B. must be compatible with the pcl::ImageType enumeration (native PJSR ImageType is already 1-based/PCL)
         II.bufferSizeMB = 16;
         II.stackSizeMB = 1024;
         II.autoMemorySize = true;
         II.autoMemoryLimit = 0.75;
         II.images = WBPPUtils.enableTargetFrames( activeFrames, 2, generateDrizzle, useLN );
         // FIX: local normalization files are associated to the file item but can have a differnt path,
         // we need to override the file path generated by the WBPPUtils.enableTargetFrames function
         II.combination = engine.combination[ BPP.imageTypeIndex( imageType ) ];
         II.rejection = selectedRejection;
         II.generateRejectionMaps = embedRejectionMaps || engine.autocrop;
         II.generateDrizzleData = generateDrizzle;
         II.pcClipLow = engine.percentileLow[ BPP.imageTypeIndex( imageType ) ];
         II.pcClipHigh = engine.percentileHigh[ BPP.imageTypeIndex( imageType ) ];
         II.sigmaLow = engine.sigmaLow[ BPP.imageTypeIndex( imageType ) ];
         II.sigmaHigh = engine.sigmaHigh[ BPP.imageTypeIndex( imageType ) ];
         II.winsorizationCutoff = 5.0;
         II.linearFitLow = engine.linearFitLow[ BPP.imageTypeIndex( imageType ) ];
         II.linearFitHigh = engine.linearFitHigh[ BPP.imageTypeIndex( imageType ) ];
         II.esdOutliersFraction = engine.ESD_Outliers[ BPP.imageTypeIndex( imageType ) ];
         II.esdAlpha = engine.ESD_Significance[ BPP.imageTypeIndex( imageType ) ];
         II.rcrLimit = engine.RCR_Limit[ BPP.imageTypeIndex( imageType ) ];
         II.clipLow = true;
         II.clipHigh = true;
         II.largeScaleClipLow = false;
         II.largeScaleClipHigh = false;
         II.subtractPedestals = false;
         II.truncateOnOutOfRange = true;
         II.generate64BitResult = false;
         II.useFileThreads = true;
         II.fileThreadOverload = 1.00;
         II.weightScale = ImageIntegration.WeightScale_BWMV;

         switch ( imageType )
         {
            case ImageType.Light:
               II.minWeight = engine.minWeight; // since core 1.8.9-1
               II.normalization = ImageIntegration.AdditiveWithScaling;
               II.rejectionNormalization = ImageIntegration.Scale;
               II.largeScaleClipHigh = engine.lightsLargeScaleRejectionHigh;
               II.largeScaleClipHighProtectedLayers = engine.lightsLargeScaleRejectionLayersHigh;
               II.largeScaleClipHighGrowth = engine.lightsLargeScaleRejectionGrowthHigh;
               II.largeScaleClipLow = engine.lightsLargeScaleRejectionLow;
               II.largeScaleClipLowProtectedLayers = engine.lightsLargeScaleRejectionLayersLow;
               II.largeScaleClipLowGrowth = engine.lightsLargeScaleRejectionGrowthLow;
               II.subtractPedestals = true;
               break;
            case ImageType.Flat:
               II.normalization = ImageIntegration.Multiplicative;
               II.rejectionNormalization = ImageIntegration.EqualizeFluxes;
               II.largeScaleClipHigh = engine.flatsLargeScaleRejection;
               II.largeScaleClipHighProtectedLayers = engine.flatsLargeScaleRejectionLayers;
               II.largeScaleClipHighGrowth = engine.flatsLargeScaleRejectionGrowth;
               break;
            default:
               II.normalization = ImageIntegration.NoNormalization;
               II.rejectionNormalization = ImageIntegration.NoRejectionNormalization;
               break;
         }

         switch ( imageType )
         {
            case ImageType.Light:
               if ( engine.subframeWeightingEnabled )
               {
                  II.weightMode = [
                     ImageIntegration.PSFSignalWeight,
                     ImageIntegration.PSFSNR,
                     ImageIntegration.PSFScaleSNR,
                     ImageIntegration.SNREstimate,
                     ImageIntegration.CSVWeightsFile
                  ][ engine.subframesWeightsMethod ];
                  II.weightKeyword = BPP.Keywords.WEIGHT;
               }
               else
               {
                  II.weightMode = ImageIntegration.DontCare;
               }

               II.evaluateSNR = true;
               II.rangeClipLow = true;
               II.rangeLow = 0;
               II.rangeClipHigh = false;
               II.truncateOnOutOfRange = false;
               II.useCache = true;
               break;
            default:
               II.weightMode = ImageIntegration.DontCare;
               II.evaluateSNR = false;
               II.rangeClipLow = false;
               II.rangeClipHigh = false;
               II.useCache = false;
               break;
         }

         // finally enable local normalization if normalization files have been provided
         if ( useLN )
         {
            II.normalization = ImageIntegration.LocalNormalization;
            II.rejectionNormalization = ImageIntegration.LocalRejectionNormalization;
            // ### N.B. LN is incompatible with subtraction of pedestals. This is
            // because the LN functions have been computed with the pedestals
            // added. This applies to both rejection and output normalizations.
            II.subtractPedestals = false;
         }

         // override the II parameters
         if ( overrideIIparameters )
         {
            Object.keys( overrideIIparameters ).forEach( key =>
            {
               // must be a valid key
               if ( II[ key ] != undefined )
                  II[ key ] = overrideIIparameters[ key ];
            } );
         }

         let csvWeightsFileIsUsed = false;
         let csvWeightsFileIsUnmodified = false;
         let customFormulaPostfix = "";
         // create the weights file if needed
         if ( II.weightMode == ImageIntegration.CSVWeightsFile )
         {
            csvWeightsFileIsUsed = true;
            let newWeightsFileContents;
            if ( frameGroup.isCFA )
               newWeightsFileContents =
               activeFrames.map( frame => [ frame.current, frame.descriptor.imageWeight,
                  frame.descriptor.imageWeight, frame.descriptor.imageWeight
               ].join( ", " ) ).join( "\n" );
            else
               newWeightsFileContents = activeFrames.map( frame => [ frame.current, frame.descriptor.imageWeight ].join( ", " ) ).join( "\n" );
            let outputDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/weights" );
            customFormulaPostfix =
               ( engine.PSFSignalWeight > 0 ? "_PSFSW-" + engine.PSFSignalWeight : "" )
               + ( engine.PSFSNRWeight > 0 ? "_PSFSNR-" + engine.PSFSNRWeight : "" )
               + ( engine.SNRWeight > 0 ? "_SNRW-" + engine.SNRWeight : "" )
               + ( engine.FWHMWeight > 0 ? "_FWHM-" + engine.FWHMWeight : "" )
               + ( engine.eccentricityWeight > 0 ? "_ECC-" + engine.eccentricityWeight : "" )
               + ( engine.starsWeight > 0 ? "_STARS-" + engine.starsWeight : "" )
               + "_PED-" + engine.pedestal;

            let filePath = outputDirectory + "/" + frameGroup.folderName() + customFormulaPostfix + ".csv";
            if ( File.exists( filePath ) )
            {
               let existingWeights = File.readTextFile( filePath );
               if ( existingWeights != newWeightsFileContents )
               {
                  File.remove( filePath );
                  File.writeTextFile( filePath, newWeightsFileContents );
               }
               else
                  csvWeightsFileIsUnmodified = true;
            }
            else
               File.writeTextFile( filePath, newWeightsFileContents );
            II.csvWeightsFilePath = filePath;
         }

         /**
          * Check if valid cached data can be used, generate rejection maps is a key and has to be chcked separately since
          * the masters will change depending on this value while the II.generateRejectionMaps property may have not changed
          * since it also depends on the autocrop option.
          */

         let IISource = II.toSource( "JavaScript", "II" /*varId*/ , 0 /*indent*/ ,
            SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();

         let IIcacheKey = engine.executionCache.keyFor( IISource + "_" + customFormulaPostfix + "_" + engine.generateRejectionMaps );
         console.writeln();
         if ( engine.executionCache.hasCacheForKey( IIcacheKey ) )
         {
            console.noteln( "ImageIntegration has cached data for key ", IIcacheKey )
            // until version 2.6.1 Image Integration cache consists in the integrated image filePath
            // from 2.6.2 it become an object
            let cachedObject = engine.executionCache.cacheForKey( IIcacheKey );
            let IICacheOutputFilePath;

            if ( typeof cachedObject == typeof
               {} )
            {
               IICacheOutputFilePath = cachedObject.IICacheOutputFilePath;
               numberOfImages = cachedObject.numberOfImages;
               failedFrames = cachedObject.failedFrames;
            }

            // we can use the cache only if weights file is used and has not changed
            useCache = !csvWeightsFileIsUsed || csvWeightsFileIsUnmodified;

            // we can use the cache only if there is an unmodified master file
            useCache = useCache && engine.executionCache.isFileUnmodified( IIcacheKey, IICacheOutputFilePath );

            // the cache is valid only if all input files and the integrated file are unchanged
            for ( let i = 0;
               ( i < activeFrames.length ) && useCache; ++i )
            {
               // source images must be unchanged
               if ( !engine.executionCache.isFileUnmodified( IIcacheKey, activeFrames[ i ].current ) )
                  useCache = false;
               if ( useCache && generateDrizzle && !engine.executionCache.isFileUnmodified( IIcacheKey, activeFrames[ i ].drizzleFile ) )
                  useCache = false;
               // if using the local normalization then the source images must be unchanged
               if ( useCache && useLN && !engine.executionCache.isFileUnmodified( IIcacheKey, activeFrames[ i ].localNormalizationFile ) )
                  useCache = false;
               // keep the status monitor refreshing
               if ( i % 100 == 0 )
                  CoreApplication.processEvents();
            }

            // determine if using cache or not
            if ( useCache )
            {
               filePath = IICacheOutputFilePath;
               console.noteln( "ImageIntegration the cache is valid, skip the integration and use the cached result at path ", IICacheOutputFilePath );
            }
            else
               console.noteln( "ImageIntegration the cache is not valid, proceed with the integration" );
         }
         else
         {
            console.noteln( "ImageIntegration has no cache data for key ", IIcacheKey );
         }
         console.writeln();

         // cache the drizzle file LMD to be updated if needed
         let drizzleFileLMD = useCache
            ?
            {}
            : activeFrames.reduce( ( acc, item ) =>
            {
               if ( item.drizzleFile && item.drizzleFile.length > 0 )
                  acc[ item.drizzleFile ] = WBPPUtils.getLastModifiedDate( item.drizzleFile );
               return acc;
            },
            {} );

         // PROCEED
         console.writeln( BPP.Format.SEPARATOR2 );
         console.writeln( IISource );
         console.writeln( BPP.Format.SEPARATOR2 );

         engine.processContainer.add( II );
         engine.pipelineManager.flushProcessContainer();

         let ok = true;
         if ( useCache )
         {
            console.noteln( "** Using cached data for ImageIntegration." );
            console.noteln( "<end><cbr><br>* master " + StackEngine.imageTypeToString( imageType ) + " frame:" );
            console.noteln( "<raw>" + filePath + "</raw>" );
         }
         else
         {
            II.showImages = false;
            ok = II.executeGlobal();
            II.showImages = true;
            numberOfImages = II.numberOfImages;
         }

         if ( !ok )
         {
            console.warningln( "** Warning: ImageIntegration failed." );
            engine.processLogger.addWarning( "ImageIntegration failed." );
         }
         else if ( !useCache )
         {
            // Write master frame FITS keywords
            // Build the file name postfix

            let keywords = new Array;
            if ( FITSKeywords )
               for ( let i = 0; i < FITSKeywords.length; ++i )
                  keywords.push( FITSKeywords[ i ] );

            keywords.push( new FITSKeyword( "COMMENT", "", "PixInsight image preprocessing pipeline" ) );
            keywords.push( new FITSKeyword( "COMMENT", "", "Master frame generated with " + engine.title + " v" + engine.version ) );

            keywords.push( new FITSKeyword( "IMAGETYP", StackEngine.imageTypeToMasterKeywordValue( imageType ), "Type of image" ) );

            keywords.push( new FITSKeyword( "XBINNING", format( "%d", frameGroup.binning ), "Binning factor, horizontal axis" ) );
            keywords.push( new FITSKeyword( "YBINNING", format( "%d", frameGroup.binning ), "Binning factor, vertical axis" ) );

            keywords.push( new FITSKeyword( "FILTER", frameGroup.filter, "Filter used when taking image" ) );

            keywords.push( new FITSKeyword( "EXPTIME", format( "%.3f", frameGroup.exposureTime ), "Exposure time in seconds" ) );

            //  inject the overscan area configuration to any master BIAS, DARK and FLATS
            if ( imageType != ImageType.Light && engine.overscan.enabled )
            {
               keywords.push( new FITSKeyword( "OSIR0X0", format( "%d", engine.overscan.imageRect.x0 ), "Custom WBPP Info: overscan image rect x0" ) );
               keywords.push( new FITSKeyword( "OSIR0Y0", format( "%d", engine.overscan.imageRect.y0 ), "Custom WBPP Info: overscan image rect y0" ) );
               keywords.push( new FITSKeyword( "OSIR0X1", format( "%d", engine.overscan.imageRect.x1 ), "Custom WBPP Info: overscan image rect x1" ) );
               keywords.push( new FITSKeyword( "OSIR0Y1", format( "%d", engine.overscan.imageRect.y1 ), "Custom WBPP Info: overscan image rect y1" ) );

               for ( let i = 0; i < 4; ++i )
                  if ( engine.overscan.overscan[ i ].enabled )
                  {
                     keywords.push( new FITSKeyword( "OSSR" + i + "X0", format( "%d", engine.overscan.overscan[ i ].sourceRect.x0 ), "Custom WBPP Info: overscan source rect x0" ) );
                     keywords.push( new FITSKeyword( "OSSR" + i + "Y0", format( "%d", engine.overscan.overscan[ i ].sourceRect.y0 ), "Custom WBPP Info: overscan source rect y0" ) );
                     keywords.push( new FITSKeyword( "OSSR" + i + "X1", format( "%d", engine.overscan.overscan[ i ].sourceRect.x1 ), "Custom WBPP Info: overscan source rect x1" ) );
                     keywords.push( new FITSKeyword( "OSSR" + i + "Y1", format( "%d", engine.overscan.overscan[ i ].sourceRect.y1 ), "Custom WBPP Info: overscan source rect y1" ) );
                     keywords.push( new FITSKeyword( "OSTR" + i + "X0", format( "%d", engine.overscan.overscan[ i ].targetRect.x0 ), "Custom WBPP Info: overscan target rect x0" ) );
                     keywords.push( new FITSKeyword( "OSTR" + i + "Y0", format( "%d", engine.overscan.overscan[ i ].targetRect.y0 ), "Custom WBPP Info: overscan target rect y0" ) );
                     keywords.push( new FITSKeyword( "OSTR" + i + "X1", format( "%d", engine.overscan.overscan[ i ].targetRect.x1 ), "Custom WBPP Info: overscan target rect x1" ) );
                     keywords.push( new FITSKeyword( "OSTR" + i + "Y1", format( "%d", engine.overscan.overscan[ i ].targetRect.y1 ), "Custom WBPP Info: overscan target rect y1" ) );
                  }
            }

            // concatenate the image keywords filtering out the keywords already added that have to remain unique
            let uniqueKeywords = [ "IMAGETYP", "XBINNING", "YBINNING", "FILTER", "EXPTIME" ];
            let window = ImageWindow.windowById( II.integrationImageId );
            this.generateSignatureProperty( window );
            this.setImagePropertyString( window, "Instrument:Filter:Name", frameGroup.filter );
            window.keywords = keywords.concat( window.keywords.filter( k => uniqueKeywords.indexOf( k.name ) == -1 ) );

            // for masterFlat if overscan is enabled we temporarily set the group size to the overscan region to generate the proper master file
            let fileName = "";
            if ( desiredFileName == undefined
               && ( frameGroup.imageType == ImageType.Flat || frameGroup.imageType == ImageType.Light )
               && engine.overscan.enabled )
            {
               let W = frameGroup.size.width;
               let H = frameGroup.size.height;
               frameGroup.size.width = engine.overscan.imageRect.x1 - engine.overscan.imageRect.x0;
               frameGroup.size.height = engine.overscan.imageRect.y1 - engine.overscan.imageRect.y0;
               fileName = desiredFileName || frameGroup.folderName( false /* sanitized */ );
               frameGroup.size.width = W;
               frameGroup.size.height = H;
            }
            else
            {
               fileName = desiredFileName || frameGroup.folderName( false /* sanitized */ );
            }
            let prefix = customPrefix != undefined ? customPrefix : "master";
            let fullFileName = prefix + fileName + ( customPostfix || "" ) + ".xisf";
            // ensure file name uniqueness
            filePath = WBPPUtils.existingAndUniqueFileName( engine.outputDirectory + "/master", fullFileName );

            console.noteln( "<end><cbr><br>* Writing master " + StackEngine.imageTypeToString( imageType ) + " frame:" );
            console.noteln( "<raw>" + filePath + "</raw>" );

            // extract the rejection map windows
            let rejectionLowWindow = null;
            let rejectionHighWindow = null;

            if ( II.generateRejectionMaps )
            {
               if ( II.clipLow )
                  rejectionLowWindow = ImageWindow.windowById( II.lowRejectionMapImageId );
               if ( II.clipHigh && embedRejectionMaps )
                  rejectionHighWindow = ImageWindow.windowById( II.highRejectionMapImageId );

               this.writeImage( filePath,
                  [ window, rejectionLowWindow, rejectionHighWindow ],
                  [ "integration", "rejection_low", "rejection_high" ] );

               if ( rejectionLowWindow != null && !rejectionLowWindow.isNull )
                  rejectionLowWindow.forceClose();
               if ( rejectionHighWindow != null && !rejectionHighWindow.isNull )
                  rejectionHighWindow.forceClose();
            }
            else
            {
               this.writeImage( filePath, [ window ], [ "integration" ] );
            }

            window.forceClose();

            // store the cached data
            if ( File.exists( filePath ) )
            {
               console.writeln();
               engine.executionCache.cacheFileLMD( IIcacheKey, filePath );
               let failedFrames = [];
               for ( let i = 0; i < activeFrames.length; ++i )
               {
                  // cache the current input frames
                  engine.executionCache.cacheFileLMD( IIcacheKey, activeFrames[ i ].current );
                  if ( generateDrizzle )
                     engine.executionCache.cacheFileLMD( IIcacheKey, activeFrames[ i ].drizzleFile );
                  if ( useLN )
                     engine.executionCache.cacheFileLMD( IIcacheKey, activeFrames[ i ].localNormalizationFile );

                  // update the cache for the drizzle file since ImageIntegration modified it (registration will keep it cached)
                  let lastLMD = drizzleFileLMD[ activeFrames[ i ].drizzleFile ];
                  if ( generateDrizzle && lastLMD )
                  {
                     let newLMD = WBPPUtils.getLastModifiedDate( activeFrames[ i ].drizzleFile );
                     if ( newLMD == lastLMD )
                     {
                        // drizzle file has not changed, we assume that it was excluded from the integration because of low weight.
                        activeFrames[ i ].processingFailed();
                        failedFrames.push( i );
                     }
                     else
                        engine.executionCache.updateLMD( activeFrames[ i ].drizzleFile, lastLMD, newLMD );
                  }
               }
               console.writeln();

               // set the cache
               engine.executionCache.setCache( IIcacheKey,
               {
                  IICacheOutputFilePath: filePath,
                  numberOfImages: numberOfImages,
                  failedFrames: failedFrames
               } );
            }
         }
         else
         {
            // we pick from the cache the failed frames and make them fail. This is needed because in the cached
            // integration execution some frames may have been discarded because of the low weight, so we need
            // to replicate this failure also for the cached frames
            for ( let i = 0; i < failedFrames.length; ++i )
               activeFrames[ failedFrames[ i ] ].processingFailed();
         }
      }

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End integration of " + StackEngine.imageTypeToString( imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      return {
         masterFilePath: filePath,
         cached: useCache,
         numberOfImages: numberOfImages
      };
   }

   // ........................................................................

   /**
    * Performs the fast integration of a group.
    *
    * @param {*} frameGroup
    * @param {*} referenceFramePath
    * @return {*}
    */
   doFastIntegration( frameGroup, referenceFramePath )
   {
      let engine = this.engine;
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin fast integration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );
      frameGroup.log();

      let useCache = false;
      let numberOfImages = -1;
      let failedFrames = [];
      let filePath = "";

      let activeFrames = frameGroup.activeFrames();
      let generateDrizzle = frameGroup.isDrizzleEnabled();
      let generateImages = frameGroup.fastIntegrationSaveImageEnabled();
      let outputDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/fastIntegration/" + frameGroup.folderName() );
      let FI = new FastIntegration;
      FI.inputHints = this.inputHints();
      FI.targets = WBPPUtils.enableTargetFrames( activeFrames, 2 );
      FI.referenceImage = referenceFramePath;
      FI.generateDrizzleData = generateDrizzle;
      FI.generateImages = generateImages;
      FI.generateRejectionMaps = engine.generateRejectionMaps || engine.autocrop;
      FI.outputDirectory = outputDirectory;
      FI.overwriteExistingFiles = true;
      FI.preciseAlignmentEnabled = false;
      FI.useROI = false;
      FI.maxStarSearchIterations = 2;
      FI.weightingEnabled = frameGroup.fastIntegrationData.weightingScheme != BPP.FastIntegrationWeightScheme.NONE;
      FI.weightingAlgorithm = Math.max( 0, frameGroup.fastIntegrationData.weightingScheme - 1 );
      FI.medianErrorTolerance = 4;
      FI.noiseReductionFilterRadius = 2;

      // Waiting for the "auto" mode of Fast Integration where the batch size will be computed automatically
      // estimate the memory occupation and adjust accordingly

      let ns = frameGroup.frameSize() / 4; // number of samples

      let targetBytes = ns * ( 32 / 8 );
      let rejectionBytes = ns * ( 8 / 8 );
      let registeredBytes = ns * ( 32 / 8 );
      let integratedImage = ns * ( 64 / 8 );
      let stackCountImage = ns * ( 32 / 8 );

      let fsize = targetBytes + registeredBytes + rejectionBytes;
      let availableMemory = physicalMemoryStatus().availableBytes // get the available physical memory
      // we assume to use 90% of the free memory
      let maxFrames = Math.floor( ( availableMemory * 0.9 - integratedImage - stackCountImage ) / fsize );
      let batchSize;
      let prefetchSize;
      if ( maxFrames < 20 )
         batchSize = maxFrames;
      else if ( maxFrames < 40 )
         batchSize = 20;
      else
         batchSize = Math.min( 100, maxFrames / 2 );
      batchSize = Math.max( 10, batchSize );
      prefetchSize = Math.min( 100, Math.max( 0, maxFrames - batchSize ) );

      FI.integrationBatchSize = 10;
      FI.integrationPrefetchSize = 10;

      //

      /**
       * Check if valid cached data can be used, generate rejection maps is a key and has to be checked separately since
       * the masters will change depending on this value while the II.generateRejectionMaps property may have not changed
       * since it also depends on the autocrop option.
       */

      let FISourceForKey = FI.toSource( "JavaScript", "FI" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
      let FIcacheKey = engine.executionCache.keyFor( FISourceForKey );
      console.writeln();

      // these values are set after we generate the cache key otherwise the key could change any time depending
      // on the current memory available
      FI.integrationBatchSize = batchSize;
      FI.integrationPrefetchSize = prefetchSize;

      if ( engine.executionCache.hasCacheForKey( FIcacheKey ) )
      {
         console.noteln( "Fast Integration has cached data for key ", FIcacheKey )
         let cachedObject = engine.executionCache.cacheForKey( FIcacheKey );
         let FICacheOutputFilePath;

         if ( typeof cachedObject == typeof
            {} )
         {
            FICacheOutputFilePath = cachedObject.FICacheOutputFilePath;
            numberOfImages = cachedObject.numberOfImages;
            failedFrames = cachedObject.failedFrames;
         }

         useCache = FICacheOutputFilePath != undefined;

         // the cache is valid only if all input and output files and the integrated file are unchanged
         for ( let i = 0;
            ( i < activeFrames.length ) && useCache; ++i )
         {
            let current = activeFrames[ i ].current;
            let drizzleFilePath;
            // source images must be unchanged
            if ( !engine.executionCache.isFileUnmodified( FIcacheKey, current ) )
               useCache = false;
            if ( generateDrizzle )
            {
               let fname = File.extractNameAndExtension( current );
               fname = File.appendToName( fname, "_r" );
               let drizzleFileName = File.changeExtension( fname, ".xdrz" );
               drizzleFilePath = outputDirectory + "/" + drizzleFileName;
               if ( !File.exists( drizzleFilePath ) || !engine.executionCache.isFileUnmodified( FIcacheKey, drizzleFilePath ) )
                  useCache = false;
            }
            if ( generateImages )
            {
               let registeredImage = FI.outputDirectory + "/" + File.extractNameAndExtension( activeFrames[ i ].current );
               registeredImage = File.appendToName( registeredImage, "_r" );
               registeredImage = File.changeExtension( registeredImage, ".xisf" );
               if ( drizzleFilePath )
                  if ( File.exists( drizzleFilePath ) )
                     if ( !engine.executionCache.isFileUnmodified( FIcacheKey, registeredImage ) )
                        useCache = false;
            }
            // keep the status monitor refreshing
            if ( i % 100 == 0 )
               CoreApplication.processEvents();
         }

         // source images must be unchanged
         if ( useCache )
            useCache = engine.executionCache.isFileUnmodified( FIcacheKey, FICacheOutputFilePath );

         // determine if using cache or not
         if ( useCache )
         {
            filePath = FICacheOutputFilePath;
            console.noteln( "Fast Integration: the cache is valid, skip the integration and use the cached result at path: ", FICacheOutputFilePath );
         }
         else
            console.noteln( "Fast Integration: the cache is not valid, proceed with the integration." );
      }
      else
      {
         console.noteln( "Fast Integration has no cache data for key ", FIcacheKey );
      }
      console.writeln();

      // PROCEED
      let FISource = FI.toSource( "JavaScript", "FI" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
      console.writeln( BPP.Format.SEPARATOR2 );
      console.writeln( FISource );
      console.writeln( BPP.Format.SEPARATOR2 );

      engine.processContainer.add( FI );
      engine.pipelineManager.flushProcessContainer();

      let ok = true;
      if ( useCache )
      {
         console.noteln( "** Using cached data for Fast Integration." );
         console.noteln( "<end><cbr><br>* master " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frame:" );
         console.noteln( "<raw>" + filePath + "</raw>" );
      }
      else
      {
         FI.showImages = false;
         console.noteln( "Using batch size of ", FI.integrationBatchSize, " and prefetch size of ", FI.integrationPrefetchSize );
         ok = FI.executeGlobal();
         FI.showImages = true;
         numberOfImages = FI.numberOfImages;
      }

      if ( !ok )
      {
         console.warningln( "** Warning: FastIntegration failed." );
         engine.processLogger.addWarning( "FastIntegration failed." );
      }
      else if ( !useCache )
      {
         // Write master frame FITS keywords
         // Build the file name postfix

         let keywords = new Array;

         keywords.push( new FITSKeyword( "COMMENT", "", "PixInsight image preprocessing pipeline" ) );
         keywords.push( new FITSKeyword( "COMMENT", "", "Master frame generated with " + engine.title + " v" + engine.version ) );

         keywords.push( new FITSKeyword( "IMAGETYP", StackEngine.imageTypeToMasterKeywordValue( frameGroup.imageType ), "Type of image" ) );

         keywords.push( new FITSKeyword( "XBINNING", format( "%d", frameGroup.binning ), "Binning factor, horizontal axis" ) );
         keywords.push( new FITSKeyword( "YBINNING", format( "%d", frameGroup.binning ), "Binning factor, vertical axis" ) );

         keywords.push( new FITSKeyword( "FILTER", frameGroup.filter, "Filter used when taking image" ) );

         keywords.push( new FITSKeyword( "EXPTIME", format( "%.3f", frameGroup.exposureTime ), "Exposure time in seconds" ) );

         // concatenate the image keywords filtering out the keywords already added that have to remain unique
         let uniqueKeywords = [ "IMAGETYP", "XBINNING", "YBINNING", "FILTER", "EXPTIME" ];
         let window = ImageWindow.windowById( FI.integrationImageId );
         this.generateSignatureProperty( window );
         this.setImagePropertyString( window, "Instrument:Filter:Name", frameGroup.filter );
         window.keywords = keywords.concat( window.keywords.filter( k => uniqueKeywords.indexOf( k.name ) == -1 ) );

         let fileName = frameGroup.folderName( false /* sanitized */ );
         let fullFileName = "master" + fileName + "_fastIntegration.xisf";
         // ensure file name uniqueness
         filePath = WBPPUtils.existingAndUniqueFileName( engine.outputDirectory + "/master", fullFileName );

         console.noteln( "<end><cbr><br>* Writing master " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frame:" );
         console.noteln( "<raw>" + filePath + "</raw>" );

         // extract the rejection map windows
         if ( FI.generateRejectionMaps )
         {
            let rejectionLowWindow = ImageWindow.windowById( FI.lowRejectionMapImageId );
            let rejectionHighWindow = ImageWindow.windowById( FI.highRejectionMapImageId );

            this.writeImage( filePath,
               [ window, rejectionLowWindow, rejectionHighWindow ],
               [ "integration", "rejection_low", "rejection_high" ] );

            if ( rejectionLowWindow != null && !rejectionLowWindow.isNull )
               rejectionLowWindow.forceClose();
            if ( rejectionHighWindow != null && !rejectionHighWindow.isNull )
               rejectionHighWindow.forceClose();
         }
         else
         {
            this.writeImage( filePath, [ window ], [ "integration" ] );
         }

         window.forceClose();

         // store the cached data
         if ( File.exists( filePath ) )
         {
            console.writeln();
            engine.executionCache.cacheFileLMD( FIcacheKey, filePath );
            engine.executionCache.cacheFileLMD( FIcacheKey, referenceFramePath );
            let failedFrames = [];
            // cache the current input frames
            for ( let i = 0; i < activeFrames.length; ++i )
            {
               let current = activeFrames[ i ].current;
               engine.executionCache.cacheFileLMD( FIcacheKey, current );
               if ( generateDrizzle )
               {
                  let fname = File.extractNameAndExtension( current );
                  fname = File.appendToName( fname, "_r" );
                  let drizzleFileName = File.changeExtension( fname, ".xdrz" );
                  let drizzleFilePath = outputDirectory + "/" + drizzleFileName;
                  if ( File.exists( drizzleFilePath ) )
                  {
                     engine.executionCache.cacheFileLMD( FIcacheKey, drizzleFilePath );
                     activeFrames[ i ].addDrizzleFile( drizzleFilePath );
                  }
               }
               if ( generateImages )
               {
                  let registeredImage = FI.outputDirectory + "/" + File.extractNameAndExtension( current );
                  registeredImage = File.appendToName( registeredImage, "_r" );
                  registeredImage = File.changeExtension( registeredImage, ".xisf" );
                  engine.executionCache.cacheFileLMD( FIcacheKey, registeredImage );
               }
            }
            console.writeln();

            // set the cache
            engine.executionCache.setCache( FIcacheKey,
            {
               FICacheOutputFilePath: filePath,
               numberOfImages: numberOfImages,
               failedFrames: failedFrames
            } );
         }
         else
         {
            // master file does not exist at path
            filePath = undefined;
         }
      }
      else
      {
         // we pick from the cache the failed frames and make them fail. This is needed because in the cached
         // integration execution some frames may have been discarded because of the low weight, so we need
         // to replicate this failure also for the cached frames
         for ( let i = 0; i < failedFrames.length; ++i )
            activeFrames[ failedFrames[ i ] ].processingFailed();
         // update the drizzle files from the cache
         for ( let i = 0; i < activeFrames.length; ++i )
         {
            let current = activeFrames[ i ].current;
            if ( generateDrizzle )
            {
               let fname = File.extractNameAndExtension( current );
               fname = File.appendToName( fname, "_r" );
               let drizzleFileName = File.changeExtension( fname, ".xdrz" );
               let drizzleFilePath = outputDirectory + "/" + drizzleFileName;
               if ( File.exists( drizzleFilePath ) )
                  activeFrames[ i ].addDrizzleFile( drizzleFilePath );
            }
         }

      }

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End fast integration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      return {
         masterFilePath: filePath,
         cached: useCache,
         numberOfImages: numberOfImages
      };
   }

   // ........................................................................

   /**
    * Performs the drizzle integration.
    */
   doDrizzleIntegration( frameGroup, fast, scale, shrink, kernel, customPrefix, customPostfix, desiredFileName, overrideIIparameters, FITSKeywords )
   {
      let engine = this.engine;
      let filePath = "";
      let imageType = frameGroup.imageType;

      frameGroup.log();

      let useCache = false;

      let activeFrames = frameGroup.activeFrames().filter( f => ( f.drizzleFile != undefined && f.drizzleFile.length > 0 ) );
      if ( activeFrames.length < 3 )
      {
         console.warningln( "** Warning: Cannot apply drizzle integration to less than three frames." );
         engine.processLogger.addWarning( "Cannot apply drizzle integration to less than three frames." );

         console.noteln( "active frames:\n" )
         console.noteln( JSON.stringify( activeFrames, null, 2 ) );
      }
      else
      {
         if ( activeFrames.length < 15 )
         {
            let msg = "** Warning: it is recommended to perform drizzle integration with a set of frames larger than 15 frames "
               + "(current is " + activeFrames.length + ").";
            console.warningln( "** Warning: " + msg );
            engine.processLogger.addWarning( msg );
         }

         let useLN = activeFrames.reduce( ( acc, item ) => ( acc && ( item.localNormalizationFile != undefined ) ), true );

         let DI = new DrizzleIntegration;

         DI.inputData = activeFrames.map( f => ( [ true, f.drizzleFile, useLN ? f.localNormalizationFile : "" ] ) )
         DI.useLUT = fast;
         DI.scale = scale;
         DI.dropShrink = shrink;
         DI.kernelFunction = kernel;
         DI.enableCFA = frameGroup.isCFA
            || ( frameGroup.associatedRGBchannel == BPP.AssociatedChannel.R )
            || ( frameGroup.associatedRGBchannel == BPP.AssociatedChannel.G )
            || ( frameGroup.associatedRGBchannel == BPP.AssociatedChannel.B );

         // override the II parameters
         if ( overrideIIparameters )
            Object.keys( overrideIIparameters ).forEach( key =>
            {
               // must be a valid key
               if ( DI[ key ] != undefined )
                  DI[ key ] = overrideIIparameters[ key ];
            } );

         /**
          * Check if valid cached data can be used
          */

         let DISource = DI.toSource( "JavaScript", "DI" /*varId*/ , 0 /*indent*/ ,
            SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();

         let DIcacheKey = engine.executionCache.keyFor( DISource );
         console.writeln();
         if ( engine.executionCache.hasCacheForKey( DIcacheKey ) )
         {
            console.noteln( "DrizzleIntegration has cached data for key ", DIcacheKey )
            // Drizzle Integration cache consists in the integrated image filePath
            let DICacheOutputFilePath = engine.executionCache.cacheForKey( DIcacheKey );

            useCache = DICacheOutputFilePath != undefined;

            // the cache is valid only if all input files and the integrated file are unchanged
            for ( let i = 0; i < activeFrames.length && useCache; ++i )
            {
               // source images must be unchanged
               if ( !engine.executionCache.isFileUnmodified( DIcacheKey, activeFrames[ i ].current ) )
                  useCache = false;
               // drizzle files must be unchanged
               if ( !engine.executionCache.isFileUnmodified( DIcacheKey, activeFrames[ i ].drizzleFile ) )
                  useCache = false;
               // if using the local normalization then the source images must be unchanged
               if ( useCache && useLN && !engine.executionCache.isFileUnmodified( DIcacheKey, activeFrames[ i ].localNormalizationFile ) )
                  useCache = false;
            }

            // source images must be unchanged
            if ( useCache )
               useCache = engine.executionCache.isFileUnmodified( DIcacheKey, DICacheOutputFilePath )

            // determine if using cache or not
            if ( useCache )
            {
               filePath = DICacheOutputFilePath;
               console.noteln( "Drizzle Integration: the cache is valid, skip the drizzle integration and use the cached result." );
            }
            else
               console.noteln( "Drizzle Integration: the cache is not valid, proceed with the drizzle integration." );
         }
         else
         {
            console.noteln( "Drizzle Integration has no cache data for key ", DIcacheKey );
         }
         console.writeln();

         // PROCEED
         console.writeln( BPP.Format.SEPARATOR2 );
         console.writeln( DISource );
         console.writeln( BPP.Format.SEPARATOR2 );

         engine.processContainer.add( DI );
         engine.pipelineManager.flushProcessContainer();

         let ok = true;
         if ( useCache )
         {
            console.noteln( "** Using cached data for Drizzle Integration." );
            console.noteln( "<end><cbr><br>* master " + StackEngine.imageTypeToString( imageType ) + " frame:" );
            console.noteln( "<raw>" + filePath + "</raw>" );
         }
         else
         {
            DI.showImages = false;
            ok = DI.executeGlobal();
            DI.showImages = true;
         }

         if ( !ok )
         {
            console.warningln( "** Warning: DrizzleIntegration failed." );
            engine.processLogger.addWarning( "DrizzleIntegration failed." );
         }
         else if ( !useCache )
         {
            // Write master frame FITS keywords
            // Build the file name postfix

            let keywords = new Array;
            if ( FITSKeywords )
               for ( let i = 0; i < FITSKeywords.length; ++i )
                  keywords.push( FITSKeywords[ i ] );

            keywords.push( new FITSKeyword( "COMMENT", "", "PixInsight image preprocessing pipeline" ) );
            keywords.push( new FITSKeyword( "COMMENT", "", "Master frame generated with " + engine.title + " v" + engine.version ) );

            keywords.push( new FITSKeyword( "IMAGETYP", StackEngine.imageTypeToMasterKeywordValue( imageType ), "Type of image" ) );

            keywords.push( new FITSKeyword( "XBINNING", format( "%d", frameGroup.binning ), "Binning factor, horizontal axis" ) );
            keywords.push( new FITSKeyword( "YBINNING", format( "%d", frameGroup.binning ), "Binning factor, vertical axis" ) );

            keywords.push( new FITSKeyword( "FILTER", frameGroup.filter, "Filter used when taking image" ) );

            keywords.push( new FITSKeyword( "EXPTIME", format( "%.3f", frameGroup.exposureTime ), "Exposure time in seconds" ) );

            // concatenate the image keywords filtering out the keywords already added that have to remain unique
            let uniqueKeywords = [ "IMAGETYP", "XBINNING", "YBINNING", "FILTER", "EXPTIME" ];
            let window = ImageWindow.windowById( DI.integrationImageId );
            this.generateSignatureProperty( window );
            this.setImagePropertyString( window, "Instrument:Filter:Name", frameGroup.filter );
            let weightImage = ImageWindow.windowById( DI.weightImageId );
            window.keywords = keywords.concat( window.keywords.filter( k => uniqueKeywords.indexOf( k.name ) == -1 ) );

            // for masterFlat if overscan is enabled we temporarily set the group size to the overscan region to generate the proper master file
            let fileName = desiredFileName || frameGroup.folderName( false /* sanitized */ );
            let prefix = customPrefix != undefined ? customPrefix : "master";
            let fullFileName = prefix + fileName + ( customPostfix || "" ) + ".xisf";
            // ensure file name uniqueness
            filePath = WBPPUtils.existingAndUniqueFileName( engine.outputDirectory + "/master", fullFileName );

            console.noteln( "<end><cbr><br>* Writing master " + StackEngine.imageTypeToString( imageType ) + " frame:" );
            console.noteln( "<raw>" + filePath + "</raw>" );

            this.writeImage( filePath, [ window, weightImage ], [ "drizzle_integration", "drizzle_weights" ] );

            window.forceClose();
            if ( weightImage )
               weightImage.forceClose();

            // store the cached data
            if ( File.exists( filePath ) )
            {
               console.writeln();
               engine.executionCache.setCache( DIcacheKey, filePath );
               engine.executionCache.cacheFileLMD( DIcacheKey, filePath );
               for ( let i = 0; i < activeFrames.length; ++i )
               {
                  engine.executionCache.cacheFileLMD( DIcacheKey, activeFrames[ i ].current );
                  engine.executionCache.cacheFileLMD( DIcacheKey, activeFrames[ i ].drizzleFile );
                  if ( useLN )
                     engine.executionCache.cacheFileLMD( DIcacheKey, activeFrames[ i ].localNormalizationFile );
               }
               console.writeln();
            }
         }
      }

      return {
         masterFilePath: filePath,
         cached: useCache
      };
   }

   // ........................................................................

   /**
    * Calibrate the provided frame group.
    */
   doCalibrate( frameGroup, doMeasurements )
   {
      let engine = this.engine;
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* Begin calibration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      frameGroup.log();

      let activeFrames = frameGroup.activeFrames();
      let cg = engine.calibrationMatcher.getCalibrationGroupsFor( frameGroup );

      // -------------------------------
      // get the matching MASTER BIAS
      // -------------------------------
      let masterBias = cg.masterBias;
      let masterBiasPath = masterBias ? masterBias.fileItems[ 0 ].filePath : "";
      let masterBiasEnabled = !WBPPUtils.isEmptyString( masterBiasPath );

      // -------------------------------
      // get the matching MASTER DARK
      // -------------------------------
      let masterDark = cg.masterDark;
      let masterDarkPath = masterDark ? masterDark.fileItems[ 0 ].filePath : "";
      let masterDarkEnabled = !WBPPUtils.isEmptyString( masterDarkPath );

      if ( !frameGroup.forceNoDark )
      {
         if ( frameGroup.overrideDark )
         {
            engine.processLogger.addMessage( 'Master Dark manually assigned.' )
         }
         else
         {
            console.noteln( "Master Dark automatic match" );
            engine.processLogger.addMessage( 'Master Dark automatic match.' );
         }
      }
      else
      {
         engine.processLogger.addMessage( 'Master Dark manually disabled.' );
      }

      // -------------------------------
      // get the matching MASTER FLAT
      // -------------------------------
      // flats are enabled only when calibrating light frames
      let masterFlat = cg.masterFlat;
      let masterFlatPath = masterFlat ? masterFlat.fileItems[ 0 ].filePath : "";
      let masterFlatEnabled = !WBPPUtils.isEmptyString( masterFlatPath );

      if ( !frameGroup.forceNoFlat )
      {
         if ( frameGroup.overrideFlat )
         {
            console.noteln( "Master Flat manually assigned" );
            engine.processLogger.addMessage( 'Master Flat manually assigned.' );
         }
         else if ( frameGroup.imageType == ImageType.Light )
         {
            console.noteln( "Master Flat automatic match" );
            engine.processLogger.addMessage( 'Master Flat automatic match.' );
         }
      }
      else
      {
         console.noteln( "Master Flat manually disabled" );
         engine.processLogger.addMessage( 'Master Flat manually disabled.' );
      }

      // LOG
      engine.processLogger.addMessage( '<ul>' );
      if ( masterBiasEnabled )
      {
         console.noteln( "Master bias: " + masterBiasPath );
         engine.processLogger.addMessage( "<li>Master bias: " + masterBiasPath + '</li>' );
      }
      else
      {
         console.noteln( "Master bias: none" );
         engine.processLogger.addMessage( "<li>Master bias: none</li>" );
      }

      if ( masterDarkEnabled )
      {
         console.noteln( "* Master dark: " + masterDarkPath );
         engine.processLogger.addMessage( "<li>Master dark: " + masterDarkPath + '</li>' );
      }
      else
      {
         console.noteln( " Master dark: none" );
         engine.processLogger.addMessage( "<li>Master dark: none</li>" );
      }

      if ( masterFlatEnabled )
      {
         console.noteln( "* Master flat: " + masterFlatPath );
         engine.processLogger.addMessage( "<li>Master flat: " + masterFlatPath + '</li>' );
      }
      else
      {
         console.noteln( " Master flat: none" );
         engine.processLogger.addMessage( "<li>Master flat: none</li>" );
      }

      engine.processLogger.addMessage( '</ul>' );

      if ( !engine.overscan.enabled && !masterBiasEnabled && !masterDarkEnabled && !masterFlatEnabled )
      {
         console.warningln( "** Warning: Image calibration skipped for " + StackEngine.imageTypeToString( frameGroup.imageType ) + " of duration " + frameGroup.exposureTime + 's.' );
         engine.processLogger.addWarning( "Image calibration skipped for " + StackEngine.imageTypeToString( frameGroup.imageType ) + " of duration " + frameGroup.exposureTime + 's.' );
         console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
         console.noteln( "* End calibration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
         console.noteln( BPP.Format.SEPARATOR );
         return undefined; /* mark the calibration skipped by returning undefined */
      }

      if ( frameGroup.optimizeMasterDark )
         engine.processLogger.addMessage( "Master Dark is optimized." );

      let IC = new ImageCalibration;

      IC.enableCFA = frameGroup.isCFA
      if ( frameGroup.isCFA )
         IC.cfaPattern = frameGroup.CFAPattern; // ### N.B. Debayer and IC define compatible enumerated parameters for CFA patterns
      IC.inputHints = this.inputHints();
      IC.outputHints = this.outputHints();
      IC.masterBiasEnabled = false;
      IC.masterDarkEnabled = false;
      IC.masterFlatEnabled = false;
      IC.calibrateBias = true; // relevant if we define overscan areas
      IC.calibrateDark = engine.overscan.enabled || masterBiasEnabled; // compatibility with pre-calibrated master dark has been removed
      IC.calibrateFlat = false; // assume we have calibrated each individual flat frame
      IC.optimizeDarks = frameGroup.optimizeMasterDark;
      IC.darkOptimizationLow = engine.darkOptimizationLow;
      IC.darkOptimizationWindow = engine.darkOptimizationWindow;
      IC.separateCFAFlatScalingFactors = masterFlat ? frameGroup.isCFA : false;
      IC.flatScaleClippingFactor = 0.05;
      IC.outputExtension = ".xisf";
      IC.outputPrefix = "";
      IC.outputPostfix = "_c";
      if ( doMeasurements != undefined )
         IC.evaluateNoise = IC.evaluateSignal = doMeasurements;
      else
         // N.B. For CFAs, evaluate noise and signal with Debayer instead of ImageCalibration
         IC.evaluateNoise = IC.evaluateSignal = frameGroup.imageType == ImageType.Light && !frameGroup.isCFA && engine.subframeWeightingEnabled;
      IC.outputSampleFormat = ImageCalibration.f32;
      IC.overwriteExistingFiles = false;
      IC.onError = ImageCalibration.Continue;

      if ( frameGroup.imageType == ImageType.Light )
      {
         let lightOutputPedestalLogMessage;
         if ( frameGroup.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Auto )
            lightOutputPedestalLogMessage = format( "Light Output Pedestal: auto" );
         else
            lightOutputPedestalLogMessage = format( "Light Output Pedestal: %.0f", frameGroup.lightOutputPedestal );
         engine.processLogger.addMessage( lightOutputPedestalLogMessage );
         console.noteln( lightOutputPedestalLogMessage );
         IC.outputPedestal = frameGroup.lightOutputPedestal;
         IC.outputPedestalMode = frameGroup.lightOutputPedestalMode;
         IC.autoPedestalLimit = frameGroup.lightOutputPedestalLimit;

         // Cosmetic Correction enabling
         IC.cosmeticCorrectionHigh = frameGroup.ccData.enabled;
         IC.cosmeticHighSigma = frameGroup.ccData.highSigma;
      }

      if ( engine.overscan.enabled )
      {
         IC.overscanEnabled = true;
         IC.overscanImageX0 = engine.overscan.imageRect.x0;
         IC.overscanImageY0 = engine.overscan.imageRect.y0;
         IC.overscanImageX1 = engine.overscan.imageRect.x1;
         IC.overscanImageY1 = engine.overscan.imageRect.y1;
         IC.overscanRegions = [ // enabled, sourceX0, sourceY0, sourceX1, sourceY1, targetX0, targetY0, targetX1, targetY1
            [ false, 0, 0, 0, 0, 0, 0, 0, 0 ],
            [ false, 0, 0, 0, 0, 0, 0, 0, 0 ],
            [ false, 0, 0, 0, 0, 0, 0, 0, 0 ],
            [ false, 0, 0, 0, 0, 0, 0, 0, 0 ]
         ];

         for ( let i = 0; i < 4; ++i )
            if ( engine.overscan.overscan[ i ].enabled )
            {
               let M = IC.overscanRegions;
               M[ i ] = [
                  true,
                  engine.overscan.overscan[ i ].sourceRect.x0,
                  engine.overscan.overscan[ i ].sourceRect.y0,
                  engine.overscan.overscan[ i ].sourceRect.x1,
                  engine.overscan.overscan[ i ].sourceRect.y1,
                  engine.overscan.overscan[ i ].targetRect.x0,
                  engine.overscan.overscan[ i ].targetRect.y0,
                  engine.overscan.overscan[ i ].targetRect.x1,
                  engine.overscan.overscan[ i ].targetRect.y1
               ];
               IC.overscanRegions = M;
            }
      }

      // Set master files
      IC.masterBiasEnabled = masterBiasEnabled;
      IC.masterBiasPath = masterBiasPath

      IC.masterDarkEnabled = masterDarkEnabled;
      IC.masterDarkPath = masterDarkPath;

      IC.masterFlatEnabled = masterFlatEnabled;
      IC.masterFlatPath = masterFlatPath;

      // Set output directories
      let subfolder = frameGroup.folderName();
      IC.outputDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/calibrated/" + subfolder );

      let calibratedFiles = [];
      let ICSource = IC.toSource( "JavaScript", "IC" /*varId*/ , 0 /*indent*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim();
      console.writeln( BPP.Format.SEPARATOR2 );
      console.writeln( ICSource );
      console.writeln( BPP.Format.SEPARATOR2 );

      /*
       * Check if valid cached data can be used. Cache must exist for the same Image Calibration configuration and bias, dark and flat masters
       * must be unchanged (if provided)
       */
      let inputFiles = activeFrames.map( item => item.current );
      let filesToCalibrate = inputFiles;

      let cached = {};
      let ICCache = {};
      let ICcacheKey = engine.executionCache.keyFor( ICSource );
      if ( engine.executionCache.hasCacheForKey( ICcacheKey ) )
      {
         console.noteln( "Image Calibration has cached data for key ", ICcacheKey );

         // the precondition for using the cache is that the calibratino masters have not changed
         let useCache = true;
         if ( masterBiasEnabled && !engine.executionCache.isFileUnmodified( ICcacheKey, masterBiasPath ) )
         {
            console.noteln( "Image Calibration master bias has changed, recalibrate all frames" );
            useCache = false;
         }
         if ( masterDarkEnabled && !engine.executionCache.isFileUnmodified( ICcacheKey, masterDarkPath ) )
         {
            console.noteln( "Image Calibration master dark has changed, recalibrate all frames" );
            useCache = false;
         }
         if ( masterFlatEnabled && !engine.executionCache.isFileUnmodified( ICcacheKey, masterFlatPath ) )
         {
            console.noteln( "Image Calibration master flat has changed, recalibrate all frames" );
            useCache = false;
         }

         if ( useCache )
         {
            ICCache = engine.executionCache.cacheForKey( ICcacheKey );
            filesToCalibrate = [];

            for ( let i = 0; i < inputFiles.length; ++i )
            {
               let inputFile = inputFiles[ i ];
               let outputFile = ICCache[ inputFile ];

               if ( outputFile != undefined
                  && engine.executionCache.isFileUnmodified( ICcacheKey, inputFile )
                  && engine.executionCache.isFileUnmodified( ICcacheKey, outputFile ) )
               {
                  cached[ inputFile ] = outputFile;
                  console.noteln( "Image Calibration will use cache for file: ", File.extractNameAndExtension( inputFile ) );
               }
               else
               {
                  console.noteln( "Image Calibration will calibrate: ", File.extractNameAndExtension( inputFile ) );
                  filesToCalibrate.push( inputFile );
               }
            }
         }
      }
      else
         console.noteln( "Image Calibration has no cached data for key ", ICcacheKey );

      // in process container we store the full calibrated files
      IC.targetFrames = WBPPUtils.enableTargetFrames( inputFiles, 2 );
      engine.processContainer.add( IC );
      engine.pipelineManager.flushProcessContainer();

      // set the files to be calibrated and proceed
      let success = true;
      if ( filesToCalibrate.length > 0 )
      {
         IC.targetFrames = WBPPUtils.enableTargetFrames( filesToCalibrate, 2 );
         success = IC.executeGlobal();
      }
      let nCached = 0;
      let nGenerated = 0;
      let nFailed = 0;

      // iterate through all input files and store cached data or the new generated ones
      let j = 0;
      for ( let i = 0; i < inputFiles.length; ++i )
      {
         let inputFile = inputFiles[ i ];
         if ( cached[ inputFile ] != undefined )
         {
            calibratedFiles.push( cached[ inputFile ] );
            nCached++;
         }
         else if ( success )
         {
            let outputFile = IC.outputData[ j++ ][ 0 ];

            console.noteln( "IC outputFile: [" + outputFile + "]" );

            if ( outputFile != undefined && outputFile.length > 0 )
            {
               if ( File.exists( outputFile ) )
               {
                  calibratedFiles.push( outputFile );

                  // update the LMD for the new generated files
                  ICCache[ inputFile ] = outputFile;
                  engine.executionCache.cacheFileLMD( ICcacheKey, inputFile );
                  engine.executionCache.cacheFileLMD( ICcacheKey, outputFile );
                  nGenerated++;
               }
               else
               {
                  calibratedFiles.push( undefined );
                  nFailed++;
               }
            }
            else
            {
               calibratedFiles.push( undefined );
               nFailed++;
            }

            console.noteln( "IC outputFile checked" );
         }
         else
         {
            calibratedFiles.push( undefined );
            nFailed++;
         }
      }
      // update the used master files LMD
      if ( masterBiasEnabled )
         engine.executionCache.cacheFileLMD( ICcacheKey, masterBiasPath );
      if ( masterDarkEnabled )
         engine.executionCache.cacheFileLMD( ICcacheKey, masterDarkPath );
      if ( masterFlatEnabled )
         engine.executionCache.cacheFileLMD( ICcacheKey, masterFlatPath );
      engine.executionCache.setCache( ICcacheKey, ICCache );
      console.noteln( nCached, " cached, ", nGenerated, " generated, ", nFailed, " failed." );

      CoreApplication.processEvents();

      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( "* End calibration of " + StackEngine.imageTypeToString( frameGroup.imageType ) + " frames" );
      console.noteln( BPP.Format.SEPARATOR );

      return {
         calibratedFiles: calibratedFiles,
         nCached: nCached,
         nGenerated: nGenerated,
         nFailed: nFailed
      };
   }

   // ........................................................................

   combineRGB( RfilePath, GfilePath, BfilePath, fileName )
   {
      let engine = this.engine;
      let filePath = engine.outputDirectory + "/master/" + fileName;

      // Check if cached data exists
      let idString = "CombinedRBG_" + RfilePath + "_" + GfilePath + "_" + BfilePath;
      let CRGBcacheKey = engine.executionCache.keyFor( idString );
      let CRBGCache = {};
      if ( engine.executionCache.hasCacheForKey( CRGBcacheKey ) )
      {

         CRBGCache = engine.executionCache.cacheForKey( CRGBcacheKey );
         if ( engine.executionCache.isFileUnmodified( CRGBcacheKey, RfilePath )
            && engine.executionCache.isFileUnmodified( CRGBcacheKey, GfilePath )
            && engine.executionCache.isFileUnmodified( CRGBcacheKey, BfilePath )
            && CRBGCache.outputFName != undefined && engine.executionCache.isFileUnmodified( CRGBcacheKey, CRBGCache.outputFName ) )
         {
            console.noteln( "RGB Combination success with cached data." );
            return {
               success: true,
               filePath: CRBGCache.outputFName,
               cached: true
            };
         }
      }

      // no cached data, create a unique file name
      filePath = WBPPUtils.existingAndUniqueFileName( engine.outputDirectory + "/master", fileName );

      // load the imagaes
      let loopData = [
      {
         c: "R",
         p: RfilePath
      },
      {
         c: "G",
         p: GfilePath
      },
      {
         c: "B",
         p: BfilePath
      } ];
      let windows = [];
      for ( let i = 0; i < 3; ++i )
      {
         let w = ImageWindow.open( loopData[ i ].p );
         if ( w.length == 0 )
         {
            for ( let j = 0; j < windows.length; ++j )
               windows[ j ].forceClose();

            return {
               error: "Unable to load " + loopData[ i ].c + " channel image at path " + loopData[ i ].p,
               success: false
            }
         }
         else
            windows.push( w[ 0 ] );
      }

      // run channel combination
      var CC = new ChannelCombination;
      CC.colorSpace = ChannelCombination.RGB;
      CC.channels = [ // enabled, id
         [ true, windows[ 0 ].mainView.id ],
         [ true, windows[ 1 ].mainView.id ],
         [ true, windows[ 2 ].mainView.id ]
      ];

      engine.processContainer.add( CC );
      engine.pipelineManager.flushProcessContainer();

      let res = CC.executeGlobal();

      if ( !res )
      {
         res = {
            error: "Channel combination failed.",
            success: false
         };
      }
      else
      {
         let rgbWindow = ImageWindow.activeWindow;

         // inject all keywords from R image to the combined image
         rgbWindow.keywords = windows[ 0 ].keywords;

         // save the file
         this.writeImage( filePath, [ rgbWindow ], [ "RGB_combination" ] );

         rgbWindow.forceClose();

         // check the result
         if ( !File.exists( filePath ) )
            res = {
               error: "Error saving the combined RGB file.",
               success: false
            };
         else
         {
            CRBGCache.outputFName = filePath;
            engine.executionCache.setCache( CRGBcacheKey, CRBGCache );
            engine.executionCache.cacheFileLMD( CRGBcacheKey, RfilePath );
            engine.executionCache.cacheFileLMD( CRGBcacheKey, GfilePath );
            engine.executionCache.cacheFileLMD( CRGBcacheKey, BfilePath );
            engine.executionCache.cacheFileLMD( CRGBcacheKey, filePath );
            res = {
               success: true,
               filePath: filePath,
               cached: false
            };
         }
      }

      // close R,G,B images
      windows[ 0 ].forceClose();
      windows[ 1 ].forceClose();
      windows[ 2 ].forceClose();

      return res;
   }

   // ........................................................................

   doLinearPatternSubtraction( groups )
   {
      let engine = this.engine;
      // first step: we need to generate the reference image. This image needs to be generated
      // for each pair binning/image size amongst the calibration groups.
      // For each binning/size we use as reference the group that has the
      // longest total exposure time since it is supposed to have the highest SNR once integrated.

      // identify the set of binning/size pairs
      let groupsByBinningAndSize = groups.filter( g =>
      {
         let isLight = g.imageType == ImageType.Light;
         let isMono = !g.isCFA;
         let isPRE = g.mode == BPP.GroupingMode.PRE;
         return isLight && isMono && isPRE;
      } ).reduce( ( acc, group ) =>
      {
         // generate an unique key that is based on binning and image size
         let key = group.binning + " (" + group.sizeString() + ")";
         if ( !acc[ key ] )
            acc[ key ] = [ group ];
         else
            acc[ key ].push( group );

         return acc;
      },
      {} );

      // iterate through all binning/size values
      let binningAndSizes = Object.keys( groupsByBinningAndSize );

      let nCached = 0;
      let nGenerated = 0;
      let nFailed = 0;

      if ( binningAndSizes.length == 0 )
      {
         console.warning( "** Warning: No monochromatic groups have been found, linear defects correction will be skipped." );
         engine.processLogger.addWarning( "No monochromatic groups have been found, linear defects correction will be skipped." );
      }
      else
      {
         // configure the LDD and LPS engines

         let LDD = new LDDEngine();
         LDD.detectionThreshold = engine.linearPatternSubtractionRejectionLimit;
         LDD.closeFormerWorkingImages = true;

         let LPS = new LPSEngine();
         LPS.targetIsActiveImage = false;
         LPS.rejectionLimit = engine.linearPatternSubtractionRejectionLimit;
         LPS.globalRejectionLimit = Math.max( 5.0, engine.linearPatternSubtractionRejectionLimit );
         LPS.closeFormerWorkingImages = true;

         let detectModes;
         switch ( engine.linearPatternSubtractionMode )
         {
            case 0: // columns
               detectModes = [
               {
                  correctColumns: true,
                  postfix: "_lps"
               } ];
               break;
            case 1: // rows
               detectModes = [
               {
                  correctColumns: false,
                  postfix: "_lps"
               } ];
               break;
            case 2: // columns and rows
               detectModes = [
               {
                  correctColumns: true,
                  postfix: "_lps"
               },
               {
                  correctColumns: false,
                  postfix: "" // on the second execution we overwrite existing files
               } ];
               break;
         }

         // execute a correction cycle for each binning/size
         for ( let i = 0; i < binningAndSizes.length; ++i )
         {
            let binning = binningAndSizes[ i ];
            let groups = groupsByBinningAndSize[ binning ];

            // sort groups by the total active duration
            let groupsSortedByDuration = groups
               .filter( g => ( g.activeFrames().length >= 3 ) )
               .map( g => (
               {
                  group: g,
                  tet: g.totalExposureTime( true /* only active frames */ )
               } ) )
               .sort( ( a, b ) =>
               {
                  if ( b.tet > a.tet )
                     return 1;
                  if ( a.tet > b.tet )
                     return -1;
                  return 0;
               } )
               .map( g => ( g.group ) );

            // check if a reference group has been found
            if ( groupsSortedByDuration.length == 0 )
            {
               console.warningln( "** Warning: Unable to generate the linear defect detection reference frame."
                  + " No groups with at least 3 grayscale light frames found. Light frames with binning " + binning
                  + " will not be corrected." );
               engine.processLogger.addError( "Unable to generate the linear defect detection reference frame."
                  + " No groups with at least 3 grayscale light frames found. Light frames with binning " + binning
                  + " will not be corrected." );
               // count the number of failed frames for the current binning
               nFailed += groups.reduce( ( acc, group ) => ( acc + group.activeFrames().length ), 0 );
               continue;
            }

            // the reference group has the longest duration
            let referenceGroup = groupsSortedByDuration[ 0 ];

            console.noteln( "LDD generate the reference frame for binning ", binning );
            // integrate the reference group to generate the reference frame for the current binninb/size value
            let
            {
               masterFilePath
            } = this.doIntegrate(
               referenceGroup,
               undefined, /* custom prefix */
               "_LDD_REFERENCE_FRAME", /* custom postfix */
               false, /* custom generate rejection maps */
               false, /* custom generate drizzle files */
               undefined, /* desired master file name */
               {
                  /* II overridden parameters */
                  combination: ImageIntegration.Average,
                  weightMode: ImageIntegration.DontCare,
                  evaluateSNR: false
               },
               undefined /* FITS keywords */
            );

            // integration check
            if ( WBPPUtils.isEmptyString( masterFilePath ) )
            {
               console.warningln( "** Warning: Failed to generate the linear defect detection reference frame."
                  + " Light frames with binning " + binning + " will not be corrected." );
               engine.processLogger.addError( "Failed to generate the linear defect detection reference frame for"
                  + " binning " + binning + "; light frames with this binning will not be corrected." );
               // count the number of failed frames for the current binning
               nFailed += groups.reduce( ( acc, group ) => ( acc + group.activeFrames().length ), 0 );
               continue;
            }

            // perform the detection for the linear defects for each mode (rows, columns or both) and generate the corresponding
            // defects list files
            let LDDdefectsFileNames = [];
            let imageReferenceWidth = 0;
            let imageReferenceHeight = 0;
            let LDDsuccess = true;
            for ( let d = 0; d < detectModes.length && LDDsuccess; ++d )
            {
               let dm = detectModes[ d ];
               LDD.detectColumns = dm.correctColumns;

               let columnOrRow = LDD.detectColumns ? "Col" : "Row";
               let LDDdefectsFileName = File.appendToName( masterFilePath, "_defects_list_" + columnOrRow );
               LDDdefectsFileName = File.changeExtension( LDDdefectsFileName, ".txt" );
               LDDdefectsFileNames[ d ] = LDDdefectsFileName;

               // generate the list of defects
               console.writeln();
               console.noteln( "Perform linear defect detection on " + columnOrRow + "s for binning ", binning );
               engine.processLogger.addSuccess( "Linear defect detection reference frame", masterFilePath );

               console.noteln( "LDD.columnOrRow  ................... ", columnOrRow );
               console.noteln( "LDD.detectColumns .................. ", LDD.detectColumns );
               console.noteln( "LDD.detectPartialLines ............. ", LDD.detectPartialLines );
               console.noteln( "LDD.imageShift ..................... ", LDD.imageShift );
               console.noteln( "LDD.closeFormerWorkingImages ....... ", LDD.closeFormerWorkingImages );
               console.noteln( "LDD.layersToRemove ................. ", LDD.layersToRemove );
               console.noteln( "LDD.rejectionLimit ................. ", LDD.rejectionLimit );
               console.noteln( "LDD.detectionThreshold ............. ", LDD.detectionThreshold );
               console.noteln( "LDD.partialLineDetectionThreshold .. ", LDD.partialLineDetectionThreshold );

               // Check if valid cache is already present for this configuration
               let LDDcacheKey = engine.executionCache.keyFor( "LDD_" + engine.linearPatternSubtractionRejectionLimit + "_" + masterFilePath );

               // cached data must exist for the current configuration
               // the reference image must be unchanged
               // the defect list file must exist and be unchanged
               console.writeln();
               console.noteln( "* LDD check for cached data." );
               if ( engine.executionCache.hasCacheForKey( LDDcacheKey )
                  && engine.executionCache.isFileUnmodified( LDDcacheKey, masterFilePath )
                  && engine.executionCache.isFileUnmodified( LDDcacheKey, LDDdefectsFileName ) )
               {
                  // valid cache exists
                  let cachedData = engine.executionCache.cacheForKey( LDDcacheKey );
                  imageReferenceWidth = cachedData.imageReferenceWidth;
                  imageReferenceHeight = cachedData.imageReferenceHeight;
                  console.noteln( "* LDD valid cached data exists, defect list file is: <raw>" + LDDdefectsFileName + "</raw>" );
                  console.writeln();
               }
               else
               {
                  // no valid cache exists, generate the defect list
                  if ( !engine.executionCache.hasCacheForKey( LDDcacheKey ) )
                     console.noteln( "* LDD has no cached data for key ", LDDcacheKey );
                  else if ( !engine.executionCache.isFileUnmodified( LDDcacheKey, masterFilePath ) )
                     console.noteln( "* LDD has cache but the reference frame has changed: ", masterFilePath );
                  else
                     console.noteln( "* LDD has cache but the defect list file has changed: <raw>" + LDDdefectsFileName + "</raw>" );
                  console.writeln();

                  // open the reference frame
                  let referenceFrameImageWindow = ImageWindow.open( masterFilePath );
                  if ( referenceFrameImageWindow.length > 0 )
                  {
                     referenceFrameImageWindow = referenceFrameImageWindow[ 0 ];
                     referenceFrameImageWindow.show();
                  }
                  else
                  {
                     LDDsuccess = false;
                     console.warningln( "** Warning: Failed to open the linear defect detection reference frame."
                        + " Light frames with binning " + binning + " will not be corrected." );
                     engine.processLogger.addError( "Failed to open the linear defect detection reference frame for"
                        + " binning " + binning + "; light frames with this binning will not be corrected." );
                     break;
                  }

                  imageReferenceWidth = referenceFrameImageWindow.mainView.image.width;
                  imageReferenceHeight = referenceFrameImageWindow.mainView.image.height;

                  // perform LDD on the active frame
                  LDD.execute();
                  referenceFrameImageWindow.forceClose();
                  console.noteln( "Linear defect detection completed." );

                  // write the defective lines
                  let LDDDefectFile = File.createFileForWriting( LDDdefectsFileName );
                  if ( LDDDefectFile )
                  {
                     console.noteln( "Linear defect detection writing defect file: <raw>" + LDDdefectsFileName + "</raw>" );
                     for ( let i = 0; i < LDD.detectedColumnOrRow.length; ++i )
                     {
                        let line = columnOrRow + " "
                           + LDD.detectedColumnOrRow[ i ] + " "
                           + LDD.detectedStartPixel[ i ] + " "
                           + LDD.detectedEndPixel[ i ];
                        LDDDefectFile.outTextLn( line );
                        console.noteln( line );
                     }
                     LDDDefectFile.close();

                     // update the cache. The cache is epmty but we need to save it anyway to remember that LDD with this configuratio has
                     // already been performed
                     let cachedData = {
                        imageReferenceWidth: imageReferenceWidth,
                        imageReferenceHeight: imageReferenceHeight
                     };
                     console.writeln();
                     engine.executionCache.setCache( LDDcacheKey, cachedData );
                     engine.executionCache.cacheFileLMD( LDDcacheKey, masterFilePath );
                     engine.executionCache.cacheFileLMD( LDDcacheKey, LDDdefectsFileName );
                     console.writeln();
                  }
                  else
                  {
                     LDDsuccess = false;
                     console.warningln( "** Warning: Linear defect detection error creating the defect file: <raw>" + LDDdefectsFileName + "</raw>" );
                     engine.processLogger.addError( "Warning: Linear defect detection error for binning " + binning + "; cannot create "
                        + "the defect file: " + LDDdefectsFileName );
                  }
               }
            }

            // we ignore the correction if LDD has not been succesfully executed
            if ( !LDDsuccess )
            {
               // count the number of failed frames for the current binning
               nFailed += groups.reduce( ( acc, group ) => ( acc + group.activeFrames().length ), 0 );
               continue;
            }

            // now that the list of defects has been succesfully generated for the current modes, we proceed correcting all frames of
            // all groups with the current binning/size
            for ( let ig = 0; ig < groups.length; ig++ )
            {
               // common mode LPS parameters
               LPS.outputDir = WBPPUtils.existingDirectory( engine.outputDirectory + "/ldd_lps/" + groups[ ig ].folderName() );
               LPS.backgroundReferenceWidth = imageReferenceWidth;
               LPS.backgroundReferenceHeight = imageReferenceHeight;

               // generate the list of active frames associated to the current group
               let activeFrames = groups[ ig ].activeFrames();

               // check for cached data
               let LPScacheKey = engine.executionCache.keyFor(
                  "LPS_"
                  + engine.linearPatternSubtractionRejectionLimit + "_"
                  + LPS.backgroundReferenceWidth + "_"
                  + LPS.backgroundReferenceHeight + "_"
                  + LPS.outputDir + "_"
                  +
                  // include the defects file names in the key
                  LDDdefectsFileNames.join( "_" )
               );

               // check the cache and skip the files that are unmodified
               let filesToCorrect = activeFrames;
               // inject an auxiliary property to track the execution of LPS
               filesToCorrect = filesToCorrect.map( item =>
               {
                  // assume files are processed succesfully by LPS
                  item.__lps_success__ = true;
                  item.__lps_input__ = item.current;
                  return item;
               } );
               let LPScacheData = {};
               // prerequisite before checking: we must have a saved cache and the defect files must me unmodified
               console.writeln();
               console.noteln( "LPS check for cached data" );
               if ( engine.executionCache.hasCacheForKey( LPScacheKey ) )
               {
                  console.noteln( "LPS has cache data for key ", LPScacheKey );

                  // check if defect files are unmodified
                  let defectFilesUnchanged = LDDdefectsFileNames.reduce( ( acc, defectFilePath ) =>
                  {
                     // skip the check if a file has already changes
                     if ( !acc )
                        return acc;
                     // check the current defect file for modifications
                     let unmodified = engine.executionCache.isFileUnmodified( LPScacheKey, defectFilePath );
                     if ( !unmodified )
                        console.noteln( "LPS cache found but the defect file has changed: ", defectFilePath );
                     return acc && unmodified;
                  }, true );

                  if ( defectFilesUnchanged )
                  {
                     // cached data is valid
                     // the cache is a map between input files and corrected files
                     LPScacheData = engine.executionCache.cacheForKey( LPScacheKey );
                     filesToCorrect = [];

                     // get the list of cached files
                     for ( let j = 0; j < activeFrames.length; ++j )
                     {
                        let activeFrame = activeFrames[ j ];
                        let outputFile = LPScacheData[ activeFrame.current ];
                        if ( outputFile != undefined
                           && engine.executionCache.isFileUnmodified( LPScacheKey, activeFrame.current )
                           && engine.executionCache.isFileUnmodified( LPScacheKey, outputFile ) )
                        {
                           // input and output files are unmodified, proceed without processing the input file again
                           activeFrame.processingSucceeded( BPP.FrameProcessingStep.LPS, outputFile );
                           nCached++;
                           console.noteln( "LPS cache found for ", activeFrame.current );
                        }
                        else
                        {
                           // put the file to be corrected into the list and store its LMD
                           filesToCorrect.push( activeFrame );
                           engine.executionCache.cacheFileLMD( LPScacheKey, activeFrame.current );
                           if ( outputFile == undefined )
                              console.noteln( "LPS no cached data for ", File.extractNameAndExtension( activeFrame.current ) );
                           else if ( !engine.executionCache.isFileUnmodified( LPScacheKey, activeFrame.current ) )
                              console.noteln( "LPS input file is modified ", File.extractNameAndExtension( activeFrame.current ) );
                           else
                              console.noteln( "LPS output file is modified ", outputFile );
                           console.noteln( "LPS will correct ", activeFrame.current );
                        }
                     }
                  }
                  else
                  {
                     console.noteln( "LPS defect files changed, LPS will be executed on all frames" );
                  }
               }
               else
               {
                  console.noteln( "LPS has no cache data for key ", LPScacheKey );
               }
               console.writeln();

               if ( filesToCorrect.length > 0 )
               {

                  // execute the correction of the group for each correction mode
                  // perform the correction passes (rows, columns or both)
                  let LPSsuccess = true;
                  for ( let d = 0; d < detectModes.length && LPSsuccess; d++ )
                  {
                     let dm = detectModes[ d ];
                     let columnOrRow = LDD.detectColumns ? "Col" : "Row";

                     // get the defects list file name for the given mode
                     let LDDdefectsFileName = LDDdefectsFileNames[ d ];

                     // keep only the files that has been succesfully processed or not yet processed
                     filesToCorrect = filesToCorrect.filter( item => item.__lps_success__ );

                     // configure LPS
                     LPS.postfix = dm.postfix;
                     LPS.correctColumns = dm.correctColumns;
                     LPS.postfix = dm.postfix;
                     LPS.defectTableFilePath = LDDdefectsFileName;

                     console.noteln( "Executing Linear Pattern Subtraction for group ", groups[ ig ].toString() );
                     console.noteln( "LPS.defectTableFilePath ........ ", LPS.defectTableFilePath );
                     console.noteln( "LPS.postfix .................... ", LPS.postfix );
                     console.noteln( "LPS.targetIsActiveImage ........ ", LPS.targetIsActiveImage );
                     console.noteln( "LPS.correctColumns ............. ", LPS.correctColumns );
                     console.noteln( "LPS.correctEntireImage ......... ", LPS.correctEntireImage );
                     console.noteln( "LPS.layersToRemove ............. ", LPS.layersToRemove );
                     console.noteln( "LPS.rejectionLimit ............. ", LPS.rejectionLimit );
                     console.noteln( "LPS.globalRejection ............ ", LPS.globalRejection );
                     console.noteln( "LPS.globalRejectionLimit ....... ", LPS.globalRejectionLimit );
                     console.noteln( "LPS.closeFormerWorkingImages ... ", LPS.closeFormerWorkingImages );
                     console.noteln( "LPS.backgroundReferenceLeft .... ", LPS.backgroundReferenceLeft );
                     console.noteln( "LPS.backgroundReferenceTop ..... ", LPS.backgroundReferenceTop );
                     console.noteln( "LPS.backgroundReferenceWidth ... ", LPS.backgroundReferenceWidth );
                     console.noteln( "LPS.backgroundReferenceHeight .. ", LPS.backgroundReferenceHeight );

                     LPS.inputFiles = filesToCorrect.map( item => item.current );
                     LPS.execute();
                     console.noteln( "Linear Pattern Subtraction completed for group ", groups[ ig ].toString() );
                     // cache the defects list LMD
                     engine.executionCache.cacheFileLMD( LPScacheKey, LDDdefectsFileName );

                     // check output results
                     if ( LPS.output.length == 0 )
                     {
                        LPSsuccess = false;
                        filesToCorrect = filesToCorrect.map( item =>
                        {
                           item.__lps_success__ = false;
                           return item;
                        } );
                        nFailed += filesToCorrect.length;
                        // report the issue
                        console.warningln( "** Warning: Linear pattern subtraction " + columnOrRow + "s failed. Light frames for group " + groups[ ig ].toString() + " will not be corrected." );
                        engine.processLogger.addError( "Linear pattern subtraction " + columnOrRow + "s failed. Light frames for group " + groups[ ig ].toString() + " will not be corrected." );
                     }
                     else
                     {
                        // create a support for output file matching
                        let LPSFilesData = LPS.output.reduce( ( acc, filePath ) =>
                        {
                           acc[ File.extractName( filePath ) ] = filePath;
                           return acc;
                        },
                        {} );

                        console.writeln();
                        for ( let c = 0; c < filesToCorrect.length; ++c )
                        {
                           let lpsFileName = File.extractName( filesToCorrect[ c ].current ) + dm.postfix;
                           let outputFilePath = LPSFilesData[ lpsFileName ];

                           if ( outputFilePath != undefined && outputFilePath.length > 0 )
                           {
                              if ( File.exists( outputFilePath ) )
                              {
                                 // success
                                 filesToCorrect[ c ].processingSucceeded( BPP.FrameProcessingStep.LPS, outputFilePath );
                                 nGenerated++;
                              }
                              else
                              {
                                 filesToCorrect[ c ].__lps_success__ = false;
                                 console.warningln( "** Warning: File does not exist after linear pattern subtraction: <raw>" + filesToCorrect[ c ].current + "</raw>" );
                                 engine.processLogger.addWarning( "File does not exist after linear pattern subtraction: " + filesToCorrect[ c ].current );
                                 nFailed++;
                              }
                           }
                           else
                           {
                              filesToCorrect[ c ].__lps_success__ = false;
                              console.warningln( "** Warning: Linear pattern subtraction failed for frame: <raw>" + filesToCorrect[ c ].current + "</raw>" );
                              engine.processLogger.addWarning( "Linear pattern subtraction failed for frame: " + filesToCorrect[ c ].current );
                              nFailed++;
                           }
                        }
                     }
                  }

                  // cache the successfully processed files
                  filesToCorrect = filesToCorrect.filter( item => item.__lps_success__ );
                  for ( let c = 0; c < filesToCorrect.length; ++c )
                  {
                     // update the cached input/output map
                     LPScacheData[ filesToCorrect[ c ].__lps_input__ ] = filesToCorrect[ c ].current;
                     // cache the final output file LMD
                     engine.executionCache.cacheFileLMD( LPScacheKey, filesToCorrect[ c ].current );
                     engine.executionCache.cacheFileLMD( LPScacheKey, filesToCorrect[ c ].__lps_input__ );
                  }
               }
               else if ( activeFrames.length > 0 )
               {
                  console.noteln( "LPS is skipped since all frames are already cached" );
               }
               else
               {
                  console.noteln( "LPS no files to correct found" );
               }

               // end processing the groups
               engine.executionCache.setCache( LPScacheKey, LPScacheData );
            }
         }
      }

      return {
         nCached: nCached,
         nGenerated: nGenerated,
         nFailed: nFailed
      };
   }

} // end of ImageProcessor class

// ----------------------------------------------------------------------------
// EOF BPP-Processing.js - Released 2026-05-10T11:05:00Z
