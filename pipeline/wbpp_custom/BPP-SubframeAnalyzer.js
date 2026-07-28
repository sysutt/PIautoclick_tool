// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-SubframeAnalyzer.js - Released 2026-05-10T11:05:00Z
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

var SubframeAnalyzer = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   // ........................................................................

   /*
    * min/max values of FWHM, eccentricity and SNR are computed.
    * These values will be used to compute the final weights of the light images.
    */
   getMinMaxDescriptorsValues( imagesDescriptors )
   {
      let FWHM = imagesDescriptors.map( descriptor => descriptor.FWHM );
      let eccentricity = imagesDescriptors.map( descriptor => descriptor.eccentricity );
      let SNR = imagesDescriptors.map( descriptor => descriptor.SNR );
      let noise = imagesDescriptors.map( descriptor => descriptor.noise );
      let stars = imagesDescriptors.map( descriptor => descriptor.numberOfStars );
      let PSFSignalWeight = imagesDescriptors.map( descriptor => descriptor.PSFSignalWeight );
      let PSFSNR = imagesDescriptors.map( descriptor => descriptor.PSFSNR );

      let FWHM_min = Math.min.apply( null, FWHM );
      let FWHM_max = Math.max.apply( null, FWHM );
      let eccentricity_min = Math.min.apply( null, eccentricity );
      let eccentricity_max = Math.max.apply( null, eccentricity );
      let SNR_min = Math.min.apply( null, SNR );
      let SNR_max = Math.max.apply( null, SNR );
      let noise_min = Math.min.apply( null, noise );
      let noise_max = Math.max.apply( null, noise );
      let stars_min = Math.min.apply( null, stars );
      let stars_max = Math.max.apply( null, stars );
      let PSFSignalWeight_min = Math.min.apply( null, PSFSignalWeight );
      let PSFSignalWeight_max = Math.max.apply( null, PSFSignalWeight );
      let PSFSNR_min = Math.min.apply( null, PSFSNR );
      let PSFSNR_max = Math.max.apply( null, PSFSNR );

      return {
         FWHM_min: FWHM_min,
         FWHM_max: FWHM_max,
         eccentricity_min: eccentricity_min,
         eccentricity_max: eccentricity_max,
         SNR_min: SNR_min,
         SNR_max: SNR_max,
         noise_min: noise_min,
         noise_max: noise_max,
         stars_min: stars_min,
         stars_max: stars_max,
         PSFSignalWeight_min: PSFSignalWeight_min,
         PSFSignalWeight_max: PSFSignalWeight_max,
         PSFSNR_min: PSFSNR_min,
         PSFSNR_max: PSFSNR_max
      };
   }

   // ........................................................................

   /*
    * Find the best frame as reference for registration across all images
    */
   findRegistrationReferenceFileItem( groups )
   {
      // extract descriptors for all active frames (double check that a descriptor exists)
      let fileItems = groups.reduce( ( acc, g ) =>
         {
            return acc.concat( g.activeFrames() );
         },
         [] ).filter( fileItem => fileItem.descriptor != undefined )

      // find the lowest binning of frames
      let binningForRegistration = fileItems.reduce( ( acc, fileItem ) =>
      {
         return Math.min( acc, fileItem.binning );
      }, 256 );

      // extract only the frames with the lowest binning
      fileItems = fileItems.filter( item => ( item.binning == binningForRegistration ) );

      // get the best frame
      let descriptors = fileItems.map( fileItem => fileItem.descriptor );
      let maxVal = 0;
      let bestFrame = undefined;

      // compute the absolute mix/max ranges
      let flatDescriptorsMinMax = this.getMinMaxDescriptorsValues( descriptors );

      // compute all images weight and find the best
      for ( let i = 0; i < fileItems.length; ++i )
      {
         // select the frame with the highest number of stars
         let weight = this.computeWeightForLight(
            fileItems[ i ].descriptor,
            flatDescriptorsMinMax,
            0, /*FWHMWeight*/
            0, /*eccentricityWeight*/
            0, /*SNRWeight*/
            1, /*starsWeight*/
            0, /*PSF Signal Weight*/
            0, /*PSF SNR Weight*/
            1 /*pedestal*/
         );
         if ( weight && isFinite( weight ) )
            if ( weight > maxVal )
            {
               maxVal = weight;
               bestFrame = fileItems[ i ];
            }
      }

      // check in case light images are all the same
      return bestFrame;
   }

   // ........................................................................

   /**
    * Calculates the weight of an image based on various quality metrics.
    *
    * @param {Object} descriptor - The file descriptor containing measured image properties
    * @param {Object} descriptorMinMax - Min/max ranges across all descriptors in the group
    * @param {Number} FWHMWeight - The Full Width at Half Maximum weight multiplier
    * @param {Number} eccentricityWeight - The eccentricity weight multiplier
    * @param {Number} SNRWeight - The Signal to Noise Ratio weight multiplier
    * @param {Number} starsWeight - The weight multiplier for number of detected stars
    * @param {Number} PSFSignalWeight - The PSF Signal weight multiplier
    * @param {Number} PSFSNRWeight - The PSF SNR weight multiplier
    * @param {Number} pedestal - The base weight value added to all scores
    * @param {Number} [normalizationFactor=1] - Factor used to normalize the final weight
    * @param {Boolean} [printToConsole=false] - Whether to print detailed weight information to console
    * @returns {Number|undefined} The calculated weight for the image, or undefined if descriptor is missing
    */
   computeWeightForLight( descriptor, descriptorMinMax, FWHMWeight, eccentricityWeight, SNRWeight, starsWeight, PSFSignalWeight, PSFSNRWeight, pedestal, normalizationFactor, printToConsole )
   {
      if ( descriptor == undefined )
         return undefined;

      normalizationFactor = normalizationFactor || 1;
      printToConsole = printToConsole || false;

      let FWHM = descriptor.FWHM;
      let FWHM_min = descriptorMinMax.FWHM_min;
      let FWHM_max = descriptorMinMax.FWHM_max;
      let eccentricity = descriptor.eccentricity;
      let eccentricity_min = descriptorMinMax.eccentricity_min;
      let eccentricity_max = descriptorMinMax.eccentricity_max;
      let SNR = descriptor.SNR;
      let SNR_min = descriptorMinMax.SNR_min;
      let SNR_max = descriptorMinMax.SNR_max;
      // let noise = descriptor.noise;
      // let noise_min = descriptorMinMax.noise_min;
      // let noise_max = descriptorMinMax.noise_max;
      let stars = descriptor.numberOfStars;
      let stars_min = descriptorMinMax.stars_min;
      let stars_max = descriptorMinMax.stars_max;
      let PSFSignal = descriptor.PSFSignalWeight;
      // let PSFSignal_min = descriptorMinMax.PSFSignalWeight_min;
      let PSFSignal_max = descriptorMinMax.PSFSignalWeight_max;
      let PSFSNR = descriptor.PSFSNR;
      // let PSFSNR_min = descriptorMinMax.PSFSNR_min;
      let PSFSNR_max = descriptorMinMax.PSFSNR_max;

      let a = FWHM_max - FWHM_min == 0 ? 0 : 1 - ( FWHM - FWHM_min ) / ( FWHM_max - FWHM_min );
      let b = eccentricity_max - eccentricity_min == 0 ? 0 : 1 - ( eccentricity - eccentricity_min ) / ( eccentricity_max - eccentricity_min );
      let c = SNR_max - SNR_min == 0 ? 0 : ( SNR - SNR_min ) / ( SNR_max - SNR_min );
      let s = stars_max - stars_min == 0 ? 0 : ( stars - stars_min ) / ( stars_max - stars_min );
      let ps = PSFSignal_max == 0 ? 0 : PSFSignal / PSFSignal_max;
      let psfsnr = PSFSNR_max == 0 ? 0 : PSFSNR / PSFSNR_max;
      let score = pedestal + a * FWHMWeight + b * eccentricityWeight + c * SNRWeight + s * starsWeight + ps * PSFSignalWeight + psfsnr * PSFSNRWeight;
      let weight = score / normalizationFactor;
      if ( printToConsole )
      {
         console.noteln( 'Weights of image: ', descriptor.filePath );
         console.noteln( "--------------------------------" );
         console.noteln( 'FWHM         : ', isFinite( a ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", a * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", FWHMWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'eccentricity : ', isFinite( b ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", b * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", eccentricityWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'SNR          : ', isFinite( c ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", c * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", SNRWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'stars        : ', isFinite( s ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", s * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", starsWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'PSF Signal   : ', isFinite( ps ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", ps * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", PSFSignalWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'PSF SNR      : ', isFinite( psfsnr ) ? WBPPUtils.paddedStringNumber( format( "%.02f %%", psfsnr * 100 ), 4 ) + " [ " + WBPPUtils.paddedStringNumber( format( "%i", PSFSNRWeight ), 3 ) + " ] " : '-' );
         console.noteln( 'Pedestal     : ', WBPPUtils.paddedStringNumber( format( "%i", pedestal ), 4 ) );
         console.noteln();
         console.noteln( 'Score        : ', isFinite( score ) ? WBPPUtils.paddedStringNumber( format( "%.03f", score ), 4 ) : '-' );
         console.noteln( 'Image weight : ', isFinite( weight ) ? WBPPUtils.paddedStringNumber( format( "%.03f", weight ), 4 ) : '-' );
         console.noteln( "--------------------------------" );
         console.flush();
      }
      return weight;
   }

   // ........................................................................

   /**
    * Writes the weights for each provided groups,
    *
    * @param {*} groups
    */
   writeWeightsWithDescriptors( groups )
   {
      let engine = this.engine;

      // compute weights for all groups
      for ( let i = 0; i < groups.length; ++i )
      {
         let activeFrames = groups[ i ].activeFrames();
         let virtualGroup = groups[ i ].isVirtual();

         for ( let j = 0; j < activeFrames.length; ++j )
         {
            CoreApplication.processEvents();

            let descriptor = activeFrames[ j ].descriptor;
            if ( descriptor && descriptor.formulaWeight != undefined && descriptor.imageWeight != undefined )
            {
               // avoid to overwrite unprocessed files (potentially original data)
               let targetFname;
               if ( virtualGroup || activeFrames[ j ].isProcessed() )
               {
                  targetFname = activeFrames[ j ].current;
               }
               else
               {
                  let subfolder = groups[ i ].folderName();
                  let measuredDirectory = WBPPUtils.existingDirectory( engine.outputDirectory + "/measured/" + subfolder );
                  targetFname = measuredDirectory + "/" + activeFrames[ j ].currentFileName();
               }

               // check if this weight has already been cached for the source and target frames
               let key = activeFrames[ j ].current + "_" + targetFname + "_" + JSON.stringify( descriptor );
               let cacheKey = engine.executionCache.keyFor( key );
               if (
                  engine.executionCache.isFileUnmodified( cacheKey, activeFrames[ j ].current )
                  && engine.executionCache.isFileUnmodified( cacheKey, targetFname )
               )
               {
                  console.noteln( "descriptor, source and target frame are unchanged, no need to write the weights into the target file" )
                  activeFrames[ j ].processingSucceeded( BPP.FrameProcessingStep.WRITE_WEIGHTS, targetFname );
               }
               else
               {

                  let imageWindow = engine.imageProcessor.readImage( activeFrames[ j ].current, "" );
                  if ( imageWindow === null )
                  {
                     console.warningln( "** Warning: Unable to open file to write weights: <raw>" + activeFrames[ j ].current + "</raw>; light frame will be discarded." );
                     engine.processLogger.addWarning( "Unable to open file to write weights: " + activeFrames[ j ].current + "; light frame will be discarded." );
                     // can't read the file, discard it
                     activeFrames[ j ].processingFailed();
                  }
                  else
                  {

                     if ( isFinite( descriptor.formulaWeight ) )
                     {
                        imageWindow.keywords = imageWindow.keywords.filter( keyword =>
                        {
                           return keyword.name != BPP.Keywords.MEASUREMENT_FWHM
                              && keyword.name != BPP.Keywords.MEASUREMENT_ECCENTRICITY
                              && keyword.name != BPP.Keywords.MEASUREMENT_NOISE
                              && keyword.name != BPP.Keywords.MEASUREMENT_SNRWEIGHT
                              && keyword.name != BPP.Keywords.MEASUREMENT_STARS
                              && keyword.name != BPP.Keywords.MEASUREMENT_PSFSIGNAL
                              && keyword.name != BPP.Keywords.MEASUREMENT_PSFSNR
                              && keyword.name != BPP.Keywords.MEASUREMENT_SCORE
                              && keyword.name != BPP.Keywords.WEIGHT;
                        } ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_FWHM,
                              format( "%.5e", descriptor.FWHM ).replace( "e", "E" ),
                              "WBPP Measurement: FWHM"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_ECCENTRICITY,
                              format( "%.5e", descriptor.eccentricity ).replace( "e", "E" ),
                              "WBPP Measurement: eccentricity"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_NOISE,
                              format( "%.5e", descriptor.noise ).replace( "e", "E" ),
                              "WBPP Measurement: noise"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_SNRWEIGHT,
                              format( "%.5e", descriptor.SNR ).replace( "e", "E" ),
                              "WBPP Measurement: SNR Weight"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_STARS,
                              format( "%i", descriptor.numberOfStars ),
                              "WBPP Measurement: number of stars found"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_PSFSIGNAL,
                              format( "%.5e", descriptor.PSFSignalWeight ).replace( "e", "E" ),
                              "WBPP Measurement: PSF Signal Weight"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_PSFSNR,
                              format( "%.5e", descriptor.PSFSNR ).replace( "e", "E" ),
                              "WBPP Measurement: PSF SNR"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.MEASUREMENT_SCORE,
                              format( "%.5e", descriptor.formulaWeight ).replace( "e", "E" ),
                              "WBPP Measurement: Image score"
                           ) ).concat(
                           new FITSKeyword(
                              BPP.Keywords.WEIGHT,
                              format( "%.3e", descriptor.imageWeight ).replace( "e", "E" ),
                              "Subframe weight"
                           ) );

                        // get the current LMD of the source file before writing, file could be overwritten so we need to update the
                        // current LMD value in the cache
                        let previousLMD = WBPPUtils.getLastModifiedDate( activeFrames[ j ].current );

                        // write the file
                        imageWindow.saveAs( targetFname, false, false, false, false );
                        imageWindow.forceClose();

                        engine.executionCache.cacheFileLMD( cacheKey, targetFname );
                        engine.executionCache.cacheFileLMD( cacheKey, activeFrames[ j ].current );
                        // handle the overwriting of the file by updating the LMD of the target frame in the cache
                        if ( targetFname == activeFrames[ j ].current )
                        {
                           // files are overwritten, update the LMD of the target
                           let newLMD = WBPPUtils.getLastModifiedDate( targetFname );
                           engine.executionCache.updateLMD( targetFname, previousLMD, newLMD );
                        }
                        activeFrames[ j ].processingSucceeded( BPP.FrameProcessingStep.WRITE_WEIGHTS, targetFname );
                     }
                     else
                     {
                        console.warningln( "** Warning: Unable to open file to write weights: <raw>" + activeFrames[ j ].current + "</raw>; light frame will be discarded." );
                        engine.processLogger.addWarning( "Unable to open file to write weights: " + activeFrames[ j ].current + "; light frame will be discarded." );
                        // can't read the file, discard it
                        activeFrames[ j ].processingFailed();
                     }
                  }
               }
            }
            else
            {
               console.warningln( "** Warning: Measurement not found for image: <raw>" + activeFrames[ j ].current + "</raw>; light frame will be discarded." );
               engine.processLogger.addWarning( "Measurement not found for image: " + activeFrames[ j ].current + "; light frame will be discarded." );
               // can't find the descriptor for the file item
               activeFrames[ j ].processingFailed();
            }
         }
      }
   }

   // ........................................................................

   /**
    * Measure the provided file items and store the measurements into each
    * measured item. The measure is performed by means of the SubframeSelector
    * Process.
    *
    * @param {[FileItem]} fileItems
    * @returns the number of frames successfully measured
    */
   computeDescriptors( fileItems )
   {
      let engine = this.engine;

      let nCached = 0;
      let nMeasured = 0;
      let nFailed = 0;

      if ( !fileItems || fileItems.length == 0 )
         return {
            nCached: nCached,
            nMeasured: nMeasured,
            nFailed: nFailed
         };

      let subframes = fileItems.map( item => item.current );

      var SS = new SubframeSelector;
      SS.routine = SubframeSelector.MeasureSubframes;
      SS.nonInteractive = true; // ### since core version 1.8.8-8
      SS.cameraResolution = SubframeSelector.Bits16;
      SS.scaleUnit = SubframeSelector.ArcSeconds;
      SS.dataUnit = SubframeSelector.DataNumber;
      SS.fileCache = true;
      SS.noNoiseAndSignalWarnings = true;

      /**
       * Use the cached data for the unchanged files
       */
      let subframesToMeasure = [];
      let cachedDescriptors = {};

      let isDescriptorValid = function( descriptor )
      {
         let failed = !isFinite( descriptor.FWHM )
            || !isFinite( descriptor.eccentricity )
            || !isFinite( descriptor.numberOfStars )
            || !isFinite( descriptor.PSFSignalWeight )
            || !isFinite( descriptor.PSFSNR )
            || !isFinite( descriptor.SNR )
            || !isFinite( descriptor.median )
            || !isFinite( descriptor.mad )
            || !isFinite( descriptor.Mstar )
            || descriptor.numberOfStars <= 0;
         return !failed;
      };

      // The cache is a map between the filePath and its descriptor
      let SSCache = {};
      let SScacheKey = engine.executionCache.keyFor( "SubframeSelector" );
      console.writeln();
      console.noteln( "SS check for cached data" );
      if ( engine.executionCache.hasCacheForKey( SScacheKey ) )
      {
         console.noteln( "SS has cached data for key ", SScacheKey );
         SSCache = engine.executionCache.cacheForKey( SScacheKey );
      }
      else
         console.noteln( "SS no cached data available for key ", SScacheKey );

      for ( let i = 0; i < subframes.length; ++i )
      {
         let filePath = subframes[ i ];
         let cachedDescriptor = SSCache[ filePath ];
         if ( cachedDescriptor != undefined && engine.executionCache.isFileUnmodified( SScacheKey, filePath ) )
         {
            // we have a valid cached data for that file
            console.noteln( "SS will use cached descriptor for ", filePath );
            cachedDescriptors[ filePath ] = cachedDescriptor;
            continue;
         }
         console.noteln( "SS will measure ", filePath );
         // non existent or old cache found, we need to measure the file
         subframesToMeasure.push( filePath );
      }

      // Put the process into the process container if needed
      // We set the full list of files to be measured, disregarding the ones that have not been measured because of
      // the cache

      SS.nonInteractive = false;
      SS.subframes = WBPPUtils.enableTargetFrames( subframes, 2 );
      engine.processContainer.add( SS );
      SS.nonInteractive = true;

      // Set the frames to be measured and perform the measurements
      let success = true;
      SS.subframes = WBPPUtils.enableTargetFrames( subframesToMeasure, 2 );
      if ( subframesToMeasure.length > 0 )
         success = SS.executeGlobal();

      // NB: fixed indexes that need to be aligned with the process implementation
      let iIndex = 0;
      let iFilePath = 3;
      let iFWHM = 5;
      let iEccentricity = 6;
      let iPSFSignalWeight = 7;
      let iSNREstimate = 9;
      let iMedian = 10;
      let iMad = 11;
      let iNoise = 12;
      let iStars = 14;
      let iMstar = 26;
      let iPSFSNR = 28;

      // create a table of  descriptors, the cached descriptors are stored immediately,
      // the others are filled by scanning the SS results
      let descriptors = [];
      for ( let i = 0; i < subframes.length; ++i )
      {
         if ( cachedDescriptors[ subframes[ i ] ] != undefined )
         {
            descriptors.push( cachedDescriptors[ subframes[ i ] ] );
            nCached++;
         }
         else
         {
            descriptors.push(
            {
               filePath: subframes[ i ],
               failed: true
            } );
         }
      }

      if ( success )
      {
         // extract successful measurements
         for ( let i = 0; i < SS.measurements.length; ++i )
         {
            let index = SS.measurements[ i ][ iIndex ];
            let filePath = SS.measurements[ i ][ iFilePath ];
            let FWHM = SS.measurements[ i ][ iFWHM ];
            let eccentricity = SS.measurements[ i ][ iEccentricity ];
            let noise = SS.measurements[ i ][ iNoise ];
            let numberOfStars = SS.measurements[ i ][ iStars ];
            let PSFSignalWeight = SS.measurements[ i ][ iPSFSignalWeight ];
            let PSFSNR = SS.measurements[ i ][ iPSFSNR ];
            let SNR = SS.measurements[ i ][ iSNREstimate ];
            let median = SS.measurements[ i ][ iMedian ];
            let mad = SS.measurements[ i ][ iMad ];
            let Mstar = SS.measurements[ i ][ iMstar ];

            let descriptor = {
               filePath: filePath,
               FWHM: FWHM,
               eccentricity: eccentricity,
               noise: noise,
               numberOfStars: numberOfStars,
               PSFSignalWeight: PSFSignalWeight,
               PSFSNR: PSFSNR,
               SNR: SNR,
               median: median,
               mad: mad,
               Mstar: Mstar
            };

            descriptor.failed = !isDescriptorValid( descriptor );

            // find the index of the corresponding descriptor data in the descriptor array
            let j = descriptors.findIndex( d => d.filePath == filePath );
            if ( j < 0 )
            {
               nFailed++;
               continue;
            }

            // update the descriptor
            descriptors[ j ] = descriptor;

            if ( descriptor.failed )
               nFailed++;
            else
               nMeasured++;
         }
      }
      else
      {
         // SS failed, no measure is returned
         nFailed = subframesToMeasure.length;
      }

      // store the result in the execution cache, only valid descriptors are saved
      for ( let i = 0; i < descriptors.length; ++i )
      {
         if ( !descriptors[ i ].failed )
         {
            let filePath = descriptors[ i ].filePath;
            engine.executionCache.cacheFileLMD( SScacheKey, filePath );
            SSCache[ descriptors[ i ].filePath ] = descriptors[ i ];
         }
      }
      engine.executionCache.setCache( SScacheKey, SSCache );

      // gather measurements in file items
      for ( let i = 0; i < descriptors.length; ++i )
      {
         let descriptor = descriptors[ i ];
         console.writeln();
         console.writeln( "<end><cbr><raw>" + descriptor.filePath + "</raw>" );
         if ( descriptor.failed )
         {
            console.noteln( "Descriptor failed: " );
            console.noteln( "FWHM            : ", descriptor.FWHM );
            console.noteln( "eccentricity    : ", descriptor.eccentricity );
            console.noteln( "numberOfStars   : ", descriptor.numberOfStars );
            console.noteln( "PSFSignalWeight : ", descriptor.PSFSignalWeight );
            console.noteln( "PSFSNR          : ", descriptor.PSFSNR );
            console.noteln( "SNR             : ", descriptor.SNR );
            console.noteln( "median          : ", descriptor.median );
            console.noteln( "mad             : ", descriptor.mad );
            console.noteln( "Mstar           : ", descriptor.Mstar );

            fileItems[ i ].processingFailed();
            console.warningln( "** Warning: Failed to measure frame: <raw>" + descriptor.filePath + "</raw>; image will be ignored." );
            engine.processLogger.addWarning( "Failed to measure frame: " + descriptor.filePath + "; image will be ignored." );
            continue;
         }

         fileItems[ i ].setDescriptor( descriptor );

         let padding = descriptor.failed ? 10 : Math.floor( Math.max( 1, Math.log10( Math.max.apply( null, [ descriptor.FWHM, descriptor.eccentricity, descriptor.SNR, descriptor.numberOfStars, descriptor.PSFSignalWeight, descriptor.PSFSNR, descriptor.median * 65535, descriptor.Mstar * 65535 ] ) ) ) ) + 1;

         console.noteln( "--------------------------" + "-".repeat( padding ) );
         console.noteln( "FWHM              : ", isFinite( descriptor.FWHM ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.FWHM ), padding ) + ' [px]' : "NaN" );
         console.noteln( "Eccentricity      : ", isFinite( descriptor.eccentricity ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.eccentricity ), padding ) : "NaN" );
         console.noteln( "Number of stars   : ", isFinite( descriptor.numberOfStars ) ? WBPPUtils.paddedStringNumber( format( "%i", descriptor.numberOfStars ), padding ) : "NaN" );
         console.noteln( "PSF Signal Weight : ", isFinite( descriptor.PSFSignalWeight ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.PSFSignalWeight ), padding ) : "NaN" );
         console.noteln( "PSF SNR           : ", isFinite( descriptor.PSFSNR ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.PSFSNR ), padding ) : "NaN" );
         console.noteln( "SNR               : ", isFinite( descriptor.SNR ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.SNR ), padding ) : "NaN" );
         console.noteln( "Median (ADU)      : ", isFinite( descriptor.median ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.median * 65535 ), padding ) : "NaN" );
         console.noteln( "MAD (ADU)         : ", isFinite( descriptor.mad ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.mad * 65535 ), padding ) : "NaN" );
         console.noteln( "Mstar (ADU)       : ", isFinite( descriptor.Mstar ) ? WBPPUtils.paddedStringNumber( format( "%0.3f", descriptor.Mstar * 65535 ), padding ) : "NaN" );
         console.noteln( "--------------------------" + "-".repeat( padding ) );

         if ( i % 50 == 0 )
         {
            console.flush();
            CoreApplication.processEvents();
         }
      }

      // return the file count
      return {
         nCached: nCached,
         nMeasured: nMeasured,
         nFailed: nFailed
      };
   }

   // ........................................................................

   readableLNReferenceSelectionMethod( sanitized )
   {
      sanitized = sanitized != undefined ? sanitized : false;
      switch ( this.engine.localNormalizationBestReferenceSelectionMethod )
      {
         case BPP.LocalNormalizationRefFrameMetric.PSFSW:
            return sanitized ? "the_highest_PSF_Signal_Weight" : "the highest PSF Signal Weight";
         case BPP.LocalNormalizationRefFrameMetric.PSFSNR:
            return sanitized ? "the_highest_PSF_SNR" : "the highest PSF SNR";
         case BPP.LocalNormalizationRefFrameMetric.MSTAR:
            return sanitized ? "the_lowest_Mstar" : "the lowest M*";
         case BPP.LocalNormalizationRefFrameMetric.MEDIAN:
            return sanitized ? "the_lowest_median" : "the lowest median";
         case BPP.LocalNormalizationRefFrameMetric.STARS:
            return sanitized ? "the_highest_number_of_stars" : "the highest number of stars";
      }

      return "";
   }

   // ........................................................................

   /**
    * Returns the best active frames or the set of best active frames to be integrated to
    * generate the local normalization reference frame accordingly
    *
    * @param {*} group
    * @return {*}
    */
   sortFramesForLocalNormalizationReference( group )
   {
      let engine = this.engine;
      let activeFrames = group.activeFrames();

      // determine the measuring criteria
      let descriptorKey = "PSFSignalWeight";
      let sortByMaxVal = true;
      switch ( engine.localNormalizationBestReferenceSelectionMethod )
      {
         case BPP.LocalNormalizationRefFrameMetric.PSFSW:
            descriptorKey = "PSFSignalWeight";
            break;
         case BPP.LocalNormalizationRefFrameMetric.PSFSNR:
            descriptorKey = "PSFSNR";
            break;
         case BPP.LocalNormalizationRefFrameMetric.MSTAR:
            descriptorKey = "Mstar";
            sortByMaxVal = false;
            break;
         case BPP.LocalNormalizationRefFrameMetric.MEDIAN:
            descriptorKey = "median";
            sortByMaxVal = false;
            break;
         case BPP.LocalNormalizationRefFrameMetric.STARS:
            descriptorKey = "numberOfStars";
            break;
      }

      // sort by measuring criteria
      activeFrames.sort( ( a, b ) =>
      {
         let aVal;
         let bVal;

         aVal = a.descriptor[ descriptorKey ];
         bVal = b.descriptor[ descriptorKey ];
         return sortByMaxVal ? bVal - aVal : aVal - bVal;
      } );

      let N = 1;
      // we exclude from the count the frames with the __integrated__ property used in LN interactive mode
      // to properly compute the number of best frmes to be integrated
      let filteredActiveFrames = activeFrames.filter( f => ( f.__integrated__ == undefined ) )
      if ( filteredActiveFrames.length >= 3
         && engine.localNormalizationReferenceFrameGenerationMethod != BPP.LocalNormalizationRefFrameMethod.SINGLE_BEST )
         // determine the number of frames to be integrated
         N = Math.max( 3, Math.min( engine.localNormalizationMaxIntegratedFrames, Math.floor( filteredActiveFrames.length / 3 ) ) );

      return {
         descriptorKey: descriptorKey,
         N: N,
         activeFrames: activeFrames
      };
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-SubframeAnalyzer.js - Released 2026-05-10T11:05:00Z
