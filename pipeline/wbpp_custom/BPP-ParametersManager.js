// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ParametersManager.js - Released 2026-05-10T11:05:00Z
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

var ParametersManager = class
{
   constructor( engine )
   {
      this.engine = engine;
      this.settingsManager = new SettingsManager( this );
   }

   // ........................................................................
   // Group A: Settings persistence (delegated to SettingsManager)
   // ........................................................................

   loadSettings( skipMigration ) { this.settingsManager.loadSettings( skipMigration ); }
   saveSettings() { this.settingsManager.saveSettings(); }
   saveRunningConfiguration() { this.settingsManager.saveRunningConfiguration(); }
   hasRunningConfiguration() { return this.settingsManager.hasRunningConfiguration(); }
   restoreRunningConfiguration() { this.settingsManager.restoreRunningConfiguration(); }
   removeRunningConfiguration() { this.settingsManager.removeRunningConfiguration(); }

   // ........................................................................

   setDefaultParameters()
   {
      setDefaultParameters.apply( this.engine );
   }

   // ........................................................................

   /**
    * Import the WBPP settings from an instance.
    *
    * @param {String|Boolean} fromJSON - JSON string to import from, or false for script parameters
    * @param {Object} dottedParams - Optional object containing parameters with dots in their names
    *                                (used in automation mode since Parameters.set() doesn't accept dots)
    */
   importParameters( fromJSON, dottedParams )
   {
      let engine = this.engine;
      let parameters = WBPPUtils.parameters;

      let P = Parameters;
      if ( fromJSON )
      {
         P = WBPPUtils.JSONParameters;
         parameters = WBPPUtils.JSONParameters;
         P.clear();
         P.fromJSONtest( fromJSON );
      }
      else if ( !engine.automationMode )
      {
         this.setDefaultParameters();
         this.loadSettings();
      }

      // Helper to check for dotted parameters that couldn't be stored in native Parameters
      let hasDottedParam = function( key )
      {
         return dottedParams && dottedParams[ key ] !== undefined;
      };
      let getDottedParamBoolean = function( key )
      {
         let val = dottedParams[ key ];
         return val === true || val === "true" || val === "1";
      };
      let getDottedParamReal = function( key )
      {
         return parseFloat( dottedParams[ key ] );
      };
      let getDottedParamInteger = function( key )
      {
         return parseInt( dottedParams[ key ] );
      };
      let getDottedParamString = function( key )
      {
         return dottedParams[ key ];
      };

      let dataVersion = undefined;
      if ( P.has( "VERSION" ) )
         dataVersion = P.getString( "VERSION" );

      if ( P.has( "saveFrameGroups" ) )
         engine.saveFrameGroups = P.getBoolean( "saveFrameGroups" );

      if ( P.has( "smartNamingOverride" ) )
         engine.smartNamingOverride = P.getBoolean( "smartNamingOverride" );

      if ( P.has( "detectMasterIncludingFullPath" ) )
         engine.detectMasterIncludingFullPath = P.getBoolean( "detectMasterIncludingFullPath" );

      if ( P.has( "outputDirectory" ) )
      {
         // from version 3.0.1/1.2.1 outputDirectory is base64-encoded with UTF-8 in parameters
         let raw = P.getString( "outputDirectory" );
         if ( dataVersion == undefined || WBPPUtils.versionLT( dataVersion, engine.fastMode ? "1.2.1" : "3.0.1" ) )
            engine.outputDirectory = raw;
         else
         {
            try { engine.outputDirectory = WBPPUtils.fromBase64UTF8( raw ); }
            catch ( e ) { engine.outputDirectory = raw; }
         }
      }

      if ( P.has( "fitsCoordinateConvention" ) )
         engine.fitsCoordinateConvention = P.getInteger( "fitsCoordinateConvention" );

      if ( P.has( "generateRejectionMaps" ) )
         engine.generateRejectionMaps = P.getBoolean( "generateRejectionMaps" );

      if ( P.has( "preserveWhiteBalance" ) )
         engine.preserveWhiteBalance = P.getBoolean( "preserveWhiteBalance" );

      if ( P.has( "groupingKeywordsEnabled" ) )
         engine.groupingKeywordsEnabled = P.getBoolean( "groupingKeywordsEnabled" );

      if ( P.has( "showAstrometricInfo" ) )
         engine.showAstrometricInfo = P.getBoolean( "showAstrometricInfo" );

      if ( P.has( "darkOptimizationThreshold" ) )
         engine.darkOptimizationThreshold = P.getReal( "darkOptimizationThreshold" );

      if ( P.has( "darkOptimizationLow" ) )
         engine.darkOptimizationLow = P.getReal( "darkOptimizationLow" );

      if ( P.has( "darkExposureTolerance" ) )
         engine.darkExposureTolerance = P.getReal( "darkExposureTolerance" );

      if ( P.has( "lightExposureTolerance" ) )
         engine.lightExposureTolerance = P.getReal( "lightExposureTolerance" );

      if ( P.has( "lightExposureTolerancePost" ) )
         engine.lightExposureTolerancePost = P.getReal( "lightExposureTolerancePost" );

      if ( P.has( "overscanEnabled" ) )
         engine.overscan.enabled = P.getBoolean( "overscanEnabled" );

      for ( let i = 0; i < 4; ++i )
      {
         if ( parameters.hasIndexed( "overscanRegionEnabled", i ) )
            engine.overscan.overscan[ i ].enabled = parameters.getBooleanIndexed( "overscanRegionEnabled", i );

         if ( parameters.hasIndexed( "overscanSourceX0", i ) )
            engine.overscan.overscan[ i ].sourceRect.x0 = parameters.getIntegerIndexed( "overscanSourceX0", i );

         if ( parameters.hasIndexed( "overscanSourceY0", i ) )
            engine.overscan.overscan[ i ].sourceRect.y0 = parameters.getIntegerIndexed( "overscanSourceY0", i );

         if ( parameters.hasIndexed( "overscanSourceX1", i ) )
            engine.overscan.overscan[ i ].sourceRect.x1 = parameters.getIntegerIndexed( "overscanSourceX1", i );

         if ( parameters.hasIndexed( "overscanSourceY1", i ) )
            engine.overscan.overscan[ i ].sourceRect.y1 = parameters.getIntegerIndexed( "overscanSourceY1", i );

         if ( parameters.hasIndexed( "overscanTargetX0", i ) )
            engine.overscan.overscan[ i ].targetRect.x0 = parameters.getIntegerIndexed( "overscanTargetX0", i );

         if ( parameters.hasIndexed( "overscanTargetY0", i ) )
            engine.overscan.overscan[ i ].targetRect.y0 = parameters.getIntegerIndexed( "overscanTargetY0", i );

         if ( parameters.hasIndexed( "overscanTargetX1", i ) )
            engine.overscan.overscan[ i ].targetRect.x1 = parameters.getIntegerIndexed( "overscanTargetX1", i );

         if ( parameters.hasIndexed( "overscanTargetY1", i ) )
            engine.overscan.overscan[ i ].targetRect.y1 = parameters.getIntegerIndexed( "overscanTargetY1", i );
      }

      if ( P.has( "overscanImageX0" ) )
         engine.overscan.imageRect.x0 = P.getInteger( "overscanImageX0" );

      if ( P.has( "overscanImageY0" ) )
         engine.overscan.imageRect.y0 = P.getInteger( "overscanImageY0" );

      if ( P.has( "overscanImageX1" ) )
         engine.overscan.imageRect.x1 = P.getInteger( "overscanImageX1" );

      if ( P.has( "overscanImageY1" ) )
         engine.overscan.imageRect.y1 = P.getInteger( "overscanImageY1" );

      if ( P.has( "minWeight" ) )
         engine.minWeight = P.getReal( "minWeight" );

      for ( let i = 0; i < 4; ++i )
      {
         if ( parameters.hasIndexed( "combination", i ) )
            engine.combination[ i ] = parameters.getIntegerIndexed( "combination", i );

         if ( parameters.hasIndexed( "rejection", i ) )
            engine.rejection[ i ] = parameters.getIntegerIndexed( "rejection", i );

         if ( parameters.hasIndexed( "percentileLow", i ) )
            engine.percentileLow[ i ] = parameters.getRealIndexed( "percentileLow", i );

         if ( parameters.hasIndexed( "percentileHigh", i ) )
            engine.percentileHigh[ i ] = parameters.getRealIndexed( "percentileHigh", i );

         if ( parameters.hasIndexed( "sigmaLow", i ) )
            engine.sigmaLow[ i ] = parameters.getRealIndexed( "sigmaLow", i );

         if ( parameters.hasIndexed( "sigmaHigh", i ) )
            engine.sigmaHigh[ i ] = parameters.getRealIndexed( "sigmaHigh", i );

         if ( parameters.hasIndexed( "linearFitLow", i ) )
            engine.linearFitLow[ i ] = parameters.getRealIndexed( "linearFitLow", i );

         if ( parameters.hasIndexed( "linearFitHigh", i ) )
            engine.linearFitHigh[ i ] = parameters.getRealIndexed( "linearFitHigh", i );

         if ( parameters.hasIndexed( "ESD_Outliers", i ) )
            engine.ESD_Outliers[ i ] = parameters.getRealIndexed( "ESD_Outliers", i );

         if ( parameters.hasIndexed( "ESD_Significance", i ) )
            engine.ESD_Significance[ i ] = parameters.getRealIndexed( "ESD_Significance", i );

         if ( parameters.hasIndexed( "RCR_Limit", i ) )
            engine.RCR_Limit[ i ] = parameters.getRealIndexed( "RCR_Limit", i );
      }

      if ( P.has( "flatsLargeScaleRejection" ) )
         engine.flatsLargeScaleRejection = P.getBoolean( "flatsLargeScaleRejection" );

      if ( P.has( "flatsLargeScaleRejectionLayers" ) )
         engine.flatsLargeScaleRejectionLayers = P.getInteger( "flatsLargeScaleRejectionLayers" );

      if ( P.has( "flatsLargeScaleRejectionGrowth" ) )
         engine.flatsLargeScaleRejectionGrowth = P.getInteger( "flatsLargeScaleRejectionGrowth" );

      if ( P.has( "lightsLargeScaleRejectionHigh" ) )
         engine.lightsLargeScaleRejectionHigh = P.getBoolean( "lightsLargeScaleRejectionHigh" );

      if ( P.has( "lightsLargeScaleRejectionLayersHigh" ) )
         engine.lightsLargeScaleRejectionLayersHigh = P.getInteger( "lightsLargeScaleRejectionLayersHigh" );

      if ( P.has( "lightsLargeScaleRejectionGrowthHigh" ) )
         engine.lightsLargeScaleRejectionGrowthHigh = P.getInteger( "lightsLargeScaleRejectionGrowthHigh" );

      if ( P.has( "lightsLargeScaleRejectionLow" ) )
         engine.lightsLargeScaleRejectionLow = P.getBoolean( "lightsLargeScaleRejectionLow" );

      if ( P.has( "lightsLargeScaleRejectionLayersLow" ) )
         engine.lightsLargeScaleRejectionLayersLow = P.getInteger( "lightsLargeScaleRejectionLayersLow" );

      if ( P.has( "lightsLargeScaleRejectionGrowthLow" ) )
         engine.lightsLargeScaleRejectionGrowthLow = P.getInteger( "lightsLargeScaleRejectionGrowthLow" );

      if ( P.has( "imageRegistration" ) )
         engine.imageRegistration = P.getBoolean( "imageRegistration" );

      if ( P.has( "linearPatternSubtraction" ) )
         engine.linearPatternSubtraction = P.getBoolean( "linearPatternSubtraction" );

      if ( P.has( "linearPatternSubtractionRejectionLimit" ) )
         engine.linearPatternSubtractionRejectionLimit = P.getInteger( "linearPatternSubtractionRejectionLimit" );

      if ( P.has( "linearPatternSubtractionMode" ) )
         engine.linearPatternSubtractionMode = P.getInteger( "linearPatternSubtractionMode" );

      if ( P.has( "subframeWeightingEnabled" ) )
         engine.subframeWeightingEnabled = P.getBoolean( "subframeWeightingEnabled" );

      if ( P.has( "subframeWeightingPreset" ) )
         engine.subframeWeightingPreset = P.getInteger( "subframeWeightingPreset" );

      if ( P.has( "FWHMWeight" ) )
         engine.FWHMWeight = P.getInteger( "FWHMWeight" );

      if ( P.has( "eccentricityWeight" ) )
         engine.eccentricityWeight = P.getInteger( "eccentricityWeight" );

      if ( P.has( "SNRWeight" ) )
         engine.SNRWeight = P.getInteger( "SNRWeight" );

      if ( P.has( "starsWeight" ) )
         engine.starsWeight = P.getInteger( "starsWeight" );

      if ( P.has( "PSFSignalWeight" ) )
         engine.PSFSignalWeight = P.getInteger( "PSFSignalWeight" );

      if ( P.has( "PSFSNRWeight" ) )
         engine.PSFSNRWeight = P.getInteger( "PSFSNRWeight" );

      if ( P.has( "pedestal" ) )
         engine.pedestal = P.getInteger( "pedestal" );

      if ( P.has( "localNormalization" ) )
         engine.localNormalization = P.getBoolean( "localNormalization" );

      if ( P.has( "localNormalizationInteractiveMode" ) )
         engine.localNormalizationInteractiveMode = P.getBoolean( "localNormalizationInteractiveMode" );

      if ( P.has( "localNormalizationGenerateImages" ) )
         engine.localNormalizationGenerateImages = P.getBoolean( "localNormalizationGenerateImages" );

      if ( P.has( "localNormalizationMethod" ) )
         engine.localNormalizationMethod = P.getInteger( "localNormalizationMethod" );

      if ( P.has( "localNormalizationMaxIntegratedFrames" ) )
         engine.localNormalizationMaxIntegratedFrames = P.getInteger( "localNormalizationMaxIntegratedFrames" );

      if ( P.has( "localNormalizationBestReferenceSelectionMethod" ) )
         engine.localNormalizationBestReferenceSelectionMethod = P.getInteger( "localNormalizationBestReferenceSelectionMethod" );

      if ( P.has( "localNormalizationGridSize" ) )
         engine.localNormalizationGridSize = P.getInteger( "localNormalizationGridSize" );

      if ( P.has( "localNormalizationReferenceFrameGenerationMethod" ) )
         engine.localNormalizationReferenceFrameGenerationMethod = P.getInteger( "localNormalizationReferenceFrameGenerationMethod" );

      if ( P.has( "localNormalizationPsfType" ) )
         engine.localNormalizationPsfType = P.getInteger( "localNormalizationPsfType" );

      if ( P.has( "localNormalizationPsfGrowth" ) )
         engine.localNormalizationPsfGrowth = P.getReal( "localNormalizationPsfGrowth" );

      if ( P.has( "localNormalizationPsfMaxStars" ) )
         engine.localNormalizationPsfMaxStars = P.getInteger( "localNormalizationPsfMaxStars" );

      if ( P.has( "localNormalizationPsfMinSNR" ) )
         engine.localNormalizationPsfMinSNR = P.getReal( "localNormalizationPsfMinSNR" );

      if ( P.has( "localNormalizationPsfAllowClusteredSources" ) )
         engine.localNormalizationPsfAllowClusteredSources = P.getBoolean( "localNormalizationPsfAllowClusteredSources" );

      if ( P.has( "localNormalizationLowClippingLevel" ) )
         engine.localNormalizationLowClippingLevel = P.getReal( "localNormalizationLowClippingLevel" );

      if ( P.has( "localNormalizationHighClippingLevel" ) )
         engine.localNormalizationHighClippingLevel = P.getReal( "localNormalizationHighClippingLevel" );

      if ( P.has( "reuseLastLNReferenceFrames" ) )
         engine.reuseLastLNReferenceFrames = P.getBoolean( "reuseLastLNReferenceFrames" );

      if ( P.has( "subframesWeightsMethod" ) )
         engine.subframesWeightsMethod = P.getInteger( "subframesWeightsMethod" );

      if ( P.has( "frameSelectionEnabled" ) )
         engine.frameSelectionEnabled = P.getBoolean( "frameSelectionEnabled" );

      if ( P.has( "frameSelectionInteractive" ) )
         engine.frameSelectionInteractive = P.getBoolean( "frameSelectionInteractive" );

      // Parse individual frame selection filter parameters
      {
         let frameSelectionFilterKeys = [ "FWHM", "eccentricity", "PSFSignalWeight", "median", "numberOfStars", "custom" ];
         let hasAnyFilterParam = false;
         let filterConfigs = [];

         // Try new indexed format first (for Process Icon compatibility)
         if ( parameters.hasIndexed( "frameSelectionKey", 0 ) )
         {
            // New indexed format
            for ( let i = 0; i < frameSelectionFilterKeys.length; i++ )
            {
               let config = {
                  enabled: false,
                  key: "",
                  value: 0,
                  compareMode: 0
               };

               if ( parameters.hasIndexed( "frameSelectionKey", i ) )
               {
                  config.key = parameters.getStringIndexed( "frameSelectionKey", i );
                  hasAnyFilterParam = true;
               }
               else
                  break;

               if ( parameters.hasIndexed( "frameSelectionEnabled", i ) )
                  config.enabled = parameters.getBooleanIndexed( "frameSelectionEnabled", i );
               if ( parameters.hasIndexed( "frameSelectionValue", i ) )
                  config.value = parameters.getRealIndexed( "frameSelectionValue", i );
               if ( parameters.hasIndexed( "frameSelectionCompareMode", i ) )
                  config.compareMode = parameters.getIntegerIndexed( "frameSelectionCompareMode", i );

               if ( config.key === "custom" )
               {
                  config.isCustomFormula = true;
                  if ( parameters.hasIndexed( "frameSelectionFormula", i ) )
                     config.formula = parameters.getStringIndexed( "frameSelectionFormula", i );
                  else
                     config.formula = "";
               }

               filterConfigs.push( config );
            }
         }
         else
         {
            // Legacy dotted format for backward compatibility (JSON imports, automation mode)
            for ( let i = 0; i < frameSelectionFilterKeys.length; i++ )
            {
               let key = frameSelectionFilterKeys[ i ];
               let prefix = "frameSelection." + key + ".";
               let config = {
                  enabled: false,
                  key: key,
                  value: 0,
                  compareMode: 0
               };

               // Check both native Parameters (for JSON import) and dottedParams (for automation mode)
               if ( P.has( prefix + "enabled" ) )
               {
                  config.enabled = P.getBoolean( prefix + "enabled" );
                  hasAnyFilterParam = true;
               }
               else if ( hasDottedParam( prefix + "enabled" ) )
               {
                  config.enabled = getDottedParamBoolean( prefix + "enabled" );
                  hasAnyFilterParam = true;
               }

               if ( P.has( prefix + "value" ) )
               {
                  config.value = P.getReal( prefix + "value" );
                  hasAnyFilterParam = true;
               }
               else if ( hasDottedParam( prefix + "value" ) )
               {
                  config.value = getDottedParamReal( prefix + "value" );
                  hasAnyFilterParam = true;
               }

               if ( P.has( prefix + "compareMode" ) )
               {
                  config.compareMode = P.getInteger( prefix + "compareMode" );
                  hasAnyFilterParam = true;
               }
               else if ( hasDottedParam( prefix + "compareMode" ) )
               {
                  config.compareMode = getDottedParamInteger( prefix + "compareMode" );
                  hasAnyFilterParam = true;
               }

               // Custom formula support
               if ( key === "custom" )
               {
                  config.isCustomFormula = true;
                  if ( P.has( prefix + "formula" ) )
                  {
                     config.formula = P.getString( prefix + "formula" );
                     hasAnyFilterParam = true;
                  }
                  else if ( hasDottedParam( prefix + "formula" ) )
                  {
                     config.formula = getDottedParamString( prefix + "formula" );
                     hasAnyFilterParam = true;
                  }
                  else
                     config.formula = "";
               }

               filterConfigs.push( config );
            }
         }

         if ( hasAnyFilterParam )
            engine.frameSelectionDefaultConfig = filterConfigs;
      }

      if ( P.has( "platesolve" ) )
         engine.platesolve = P.getBoolean( "platesolve" );

      if ( P.has( "platesolveFallbackManual" ) )
         engine.platesolveFallbackManual = P.getBoolean( "platesolveFallbackManual" );

      if ( P.has( "imageSolverRa" ) )
         engine.imageSolverRa = P.getReal( "imageSolverRa" );

      if ( P.has( "imageSolverDec" ) )
         engine.imageSolverDec = P.getReal( "imageSolverDec" );

      if ( P.has( "imageSolverObservationTime" ) )
         engine.imageSolverObservationTime = P.getReal( "imageSolverObservationTime" );

      if ( P.has( "imageSolverFocalLength" ) )
         engine.imageSolverFocalLength = P.getReal( "imageSolverFocalLength" );

      if ( P.has( "imageSolverPixelSize" ) )
         engine.imageSolverPixelSize = P.getReal( "imageSolverPixelSize" );

      if ( P.has( "imageSolverForceDefaults" ) )
         engine.imageSolverForceDefaults = P.getBoolean( "imageSolverForceDefaults" );

      if ( P.has( "pixelInterpolation" ) )
         engine.pixelInterpolation = P.getInteger( "pixelInterpolation" );

      if ( P.has( "clampingThreshold" ) )
         engine.clampingThreshold = P.getReal( "clampingThreshold" );

      if ( P.has( "maxStars" ) )
         engine.maxStars = P.getInteger( "maxStars" );

      if ( P.has( "distortionCorrection" ) )
         engine.distortionCorrection = P.getBoolean( "distortionCorrection" );

      if ( P.has( "maxSplinePoints" ) )
         engine.maxSplinePoints = P.getInteger( "maxSplinePoints" );

      if ( P.has( "rigidTransformations" ) )
         engine.rigidTransformations = P.getBoolean( "rigidTransformations" );

      if ( P.has( "structureLayers" ) )
         engine.structureLayers = P.getInteger( "structureLayers" );

      if ( P.has( "hotPixelFilterRadius" ) )
         engine.hotPixelFilterRadius = P.getInteger( "hotPixelFilterRadius" );

      if ( P.has( "noiseReductionFilterRadius" ) )
         engine.noiseReductionFilterRadius = P.getInteger( "noiseReductionFilterRadius" );

      if ( P.has( "minStructureSize" ) )
         engine.minStructureSize = P.getInteger( "minStructureSize" );

      if ( P.has( "sensitivity" ) )
         engine.sensitivity = P.getReal( "sensitivity" );

      if ( P.has( "peakResponse" ) )
         engine.peakResponse = P.getReal( "peakResponse" );

      if ( P.has( "brightThreshold" ) )
         engine.brightThreshold = P.getReal( "brightThreshold" );

      if ( P.has( "maxStarDistortion" ) )
         engine.maxStarDistortion = P.getReal( "maxStarDistortion" );

      if ( P.has( "allowClusteredSources" ) )
         engine.allowClusteredSources = P.getBoolean( "allowClusteredSources" );

      if ( P.has( "useTriangleSimilarity" ) )
         engine.useTriangleSimilarity = P.getBoolean( "useTriangleSimilarity" );

      if ( P.has( "reuseLastReferenceFrames" ) )
         engine.reuseLastReferenceFrames = P.getBoolean( "reuseLastReferenceFrames" );

      if ( P.has( "referenceImage" ) )
         engine.referenceImage = P.getString( "referenceImage" );

      if ( P.has( "bestFrameReferenceKeyword" ) )
         engine.bestFrameReferenceKeyword = P.getString( "bestFrameReferenceKeyword" );

      // migration from wbpp 2.7.8 and earlier
      if ( P.has( "bestFrameRefernceMethod" ) )
         engine.bestFrameReferenceMethod = P.getInteger( "bestFrameRefernceMethod" );

      if ( P.has( "bestFrameReferenceMethod" ) )
         engine.bestFrameReferenceMethod = P.getInteger( "bestFrameReferenceMethod" );

      if ( P.has( "debayerOutputMethod" ) )
         engine.debayerOutputMethod = P.getInteger( "debayerOutputMethod" );

      if ( P.has( "integrate" ) )
         engine.integrate = P.getBoolean( "integrate" );

      if ( P.has( "autocrop" ) )
         engine.autocrop = P.getBoolean( "autocrop" );
      if ( P.has( "autoIntegrationMode" ) )
         engine.autoIntegrationMode = P.getBoolean( "autoIntegrationMode" );

      if ( P.has( "recombineRGB" ) )
         engine.recombineRGB = P.getBoolean( "recombineRGB" );

      if ( P.has( "debayerActiveChannelR" ) )
         engine.debayerActiveChannelR = P.getBoolean( "debayerActiveChannelR" );

      if ( P.has( "debayerActiveChannelG" ) )
         engine.debayerActiveChannelG = P.getBoolean( "debayerActiveChannelG" );

      if ( P.has( "debayerActiveChannelB" ) )
         engine.debayerActiveChannelB = P.getBoolean( "debayerActiveChannelB" );

      if ( P.has( "usePipelineScript" ) )
         engine.usePipelineScript = P.getBoolean( "usePipelineScript" );

      if ( P.has( "pipelineScriptFile" ) )
         engine.pipelineScriptFile = P.getString( "pipelineScriptFile" );

      if ( P.has( "usePipelineBuilderScript" ) )
         engine.usePipelineBuilderScript = P.getBoolean( "usePipelineBuilderScript" );

      if ( P.has( "pipelineBuilderScriptFile" ) )
         engine.pipelineBuilderScriptFile = P.getString( "pipelineBuilderScriptFile" );

      if ( P.has( "enableCompactGUI" ) )
         engine.enableCompactGUI = P.getBoolean( "enableCompactGUI" );

      if ( P.has( "keywords" ) )
      {
         let dataStr = WBPPUtils.fromBase64UTF8( P.getString( "keywords" ) );
         let keywords = JSON.parse( dataStr );
         engine.keywords.list = this.migrateKeywords( keywords, dataVersion );
      }

      if ( fromJSON && P.has( "testExecutionStatus" ) )
         engine.executionStatus = JSON.parse( P.getString( "testExecutionStatus" ) );

      if ( !engine.automationMode || fromJSON )
      {
         if ( P.has( "groups" ) )
            this.groupsFromStringData( WBPPUtils.fromBase64UTF8( P.getString( "groups" ) ), dataVersion );

         if ( P.has( BPP.Constants.CACHE_VERSION ) )
         // This happens only if the script has been loaded from a process icon or from an external JSON (like tests).
         {
            console.noteln( "has execution cache" );
            try
            {
               engine.executionCache.fromString( WBPPUtils.fromBase64UTF8( P.getString( BPP.Constants.CACHE_VERSION ) ) );
            }
            catch ( e )
            {
               console.warningln( "** Warning: Cache data parsing has failed." );
               engine.executionCache.reset();
            }
            engine.cacheHasBeenLoadedFromAnInstance = true;
         }

         if ( dataVersion )
            this.migrateFrom( dataVersion );
      }
   }

   // ........................................................................

   /**
    * Prepare the export of the WBPP parameters to an instance.
    *
    * @param {Boolean} toJSON if true, the function will return a json object containing the saved parameters
    */
   exportParameters( toJSON )
   {
      let engine = this.engine;
      let parameters = WBPPUtils.parameters;

      let P = Parameters;
      if ( toJSON )
      {
         P = WBPPUtils.JSONParameters;
         parameters = WBPPUtils.JSONParameters;
      }

      P.clear();

      P.set( "VERSION", engine.version );

      P.set( "saveFrameGroups", engine.saveFrameGroups );
      P.set( "smartNamingOverride", engine.smartNamingOverride );
      P.set( "detectMasterIncludingFullPath", engine.detectMasterIncludingFullPath );
      P.set( "outputDirectory", WBPPUtils.toBase64UTF8( engine.outputDirectory ) );
      P.set( "fitsCoordinateConvention", engine.fitsCoordinateConvention );
      P.set( "generateRejectionMaps", engine.generateRejectionMaps );
      P.set( "preserveWhiteBalance", engine.preserveWhiteBalance );

      P.set( "groupingKeywordsEnabled", engine.groupingKeywordsEnabled );
      P.set( "showAstrometricInfo", engine.showAstrometricInfo );

      P.set( "darkOptimizationLow", engine.darkOptimizationLow );
      P.set( "darkExposureTolerance", engine.darkExposureTolerance );

      P.set( "overscanEnabled", engine.overscan.enabled );

      for ( let i = 0; i < 4; ++i )
      {
         parameters.setIndexed( "overscanRegionEnabled", i, engine.overscan.overscan[ i ].enabled );
         parameters.setIndexed( "overscanSourceX0", i, engine.overscan.overscan[ i ].sourceRect.x0 );
         parameters.setIndexed( "overscanSourceY0", i, engine.overscan.overscan[ i ].sourceRect.y0 );
         parameters.setIndexed( "overscanSourceX1", i, engine.overscan.overscan[ i ].sourceRect.x1 );
         parameters.setIndexed( "overscanSourceY1", i, engine.overscan.overscan[ i ].sourceRect.y1 );
         parameters.setIndexed( "overscanTargetX0", i, engine.overscan.overscan[ i ].targetRect.x0 );
         parameters.setIndexed( "overscanTargetY0", i, engine.overscan.overscan[ i ].targetRect.y0 );
         parameters.setIndexed( "overscanTargetX1", i, engine.overscan.overscan[ i ].targetRect.x1 );
         parameters.setIndexed( "overscanTargetY1", i, engine.overscan.overscan[ i ].targetRect.y1 );
      }

      P.set( "overscanImageX0", engine.overscan.imageRect.x0 );
      P.set( "overscanImageY0", engine.overscan.imageRect.y0 );
      P.set( "overscanImageX1", engine.overscan.imageRect.x1 );
      P.set( "overscanImageY1", engine.overscan.imageRect.y1 );

      P.set( "minWeight", engine.minWeight );

      for ( let i = 0; i < 4; ++i )
      {
         parameters.setIndexed( "combination", i, engine.combination[ i ] );
         parameters.setIndexed( "rejection", i, engine.rejection[ i ] );
         parameters.setIndexed( "percentileLow", i, engine.percentileLow[ i ] );
         parameters.setIndexed( "percentileHigh", i, engine.percentileHigh[ i ] );
         parameters.setIndexed( "sigmaLow", i, engine.sigmaLow[ i ] );
         parameters.setIndexed( "sigmaHigh", i, engine.sigmaHigh[ i ] );
         parameters.setIndexed( "linearFitLow", i, engine.linearFitLow[ i ] );
         parameters.setIndexed( "linearFitHigh", i, engine.linearFitHigh[ i ] );
         parameters.setIndexed( "ESD_Outliers", i, engine.ESD_Outliers[ i ] );
         parameters.setIndexed( "ESD_Significance", i, engine.ESD_Significance[ i ] );
         parameters.setIndexed( "RCR_Limit", i, engine.RCR_Limit[ i ] );
      }

      P.set( "flatsLargeScaleRejection", engine.flatsLargeScaleRejection );
      P.set( "flatsLargeScaleRejectionLayers", engine.flatsLargeScaleRejectionLayers );
      P.set( "flatsLargeScaleRejectionGrowth", engine.flatsLargeScaleRejectionGrowth );

      P.set( "lightsLargeScaleRejectionHigh", engine.lightsLargeScaleRejectionHigh );
      P.set( "lightsLargeScaleRejectionLayersHigh", engine.lightsLargeScaleRejectionLayersHigh );
      P.set( "lightsLargeScaleRejectionGrowthHigh", engine.lightsLargeScaleRejectionGrowthHigh );

      P.set( "lightsLargeScaleRejectionLow", engine.lightsLargeScaleRejectionLow );
      P.set( "lightsLargeScaleRejectionLayersLow", engine.lightsLargeScaleRejectionLayersLow );
      P.set( "lightsLargeScaleRejectionGrowthLow", engine.lightsLargeScaleRejectionGrowthLow );

      P.set( "imageRegistration", engine.imageRegistration );
      P.set( "lightExposureTolerance", engine.lightExposureTolerance );
      P.set( "lightExposureTolerancePost", engine.lightExposureTolerancePost );

      P.set( "linearPatternSubtraction", engine.linearPatternSubtraction );
      P.set( "linearPatternSubtractionRejectionLimit", engine.linearPatternSubtractionRejectionLimit );
      P.set( "linearPatternSubtractionMode", engine.linearPatternSubtractionMode );
      P.set( "reuseLastLNReferenceFrames", engine.reuseLastLNReferenceFrames );

      P.set( "platesolve", engine.platesolve );
      P.set( "platesolveFallbackManual", engine.platesolveFallbackManual );
      P.set( "imageSolverRa", engine.imageSolverRa );
      P.set( "imageSolverDec", engine.imageSolverDec );
      P.set( "imageSolverObservationTime", engine.imageSolverObservationTime );
      P.set( "imageSolverFocalLength", engine.imageSolverFocalLength );
      P.set( "imageSolverPixelSize", engine.imageSolverPixelSize );
      P.set( "imageSolverForceDefaults", engine.imageSolverForceDefaults );

      P.set( "pixelInterpolation", engine.pixelInterpolation );
      P.set( "clampingThreshold", engine.clampingThreshold );
      P.set( "maxStars", engine.maxStars );
      P.set( "distortionCorrection", engine.distortionCorrection );
      P.set( "maxSplinePoints", engine.maxSplinePoints );
      P.set( "rigidTransformations", engine.rigidTransformations );
      P.set( "structureLayers", engine.structureLayers );
      P.set( "hotPixelFilterRadius", engine.hotPixelFilterRadius );
      P.set( "noiseReductionFilterRadius", engine.noiseReductionFilterRadius );
      P.set( "minStructureSize", engine.minStructureSize );
      P.set( "sensitivity", engine.sensitivity );
      P.set( "peakResponse", engine.peakResponse );
      P.set( "brightThreshold", engine.brightThreshold );
      P.set( "maxStarDistortion", engine.maxStarDistortion );
      P.set( "allowClusteredSources", engine.allowClusteredSources );
      P.set( "useTriangleSimilarity", engine.useTriangleSimilarity );
      P.set( "reuseLastReferenceFrames", engine.reuseLastReferenceFrames );

      P.set( "referenceImage", engine.referenceImage );
      P.set( "bestFrameReferenceKeyword", engine.bestFrameReferenceKeyword );
      P.set( "bestFrameReferenceMethod", engine.bestFrameReferenceMethod );
      P.set( "debayerOutputMethod", engine.debayerOutputMethod );

      P.set( "subframeWeightingEnabled", engine.subframeWeightingEnabled );
      P.set( "subframeWeightingPreset", engine.subframeWeightingPreset );
      P.set( "subframesWeightsMethod", engine.subframesWeightsMethod );
      P.set( "FWHMWeight", engine.FWHMWeight );
      P.set( "eccentricityWeight", engine.eccentricityWeight );
      P.set( "SNRWeight", engine.SNRWeight );
      P.set( "starsWeight", engine.starsWeight );
      P.set( "PSFSignalWeight", engine.PSFSignalWeight );
      P.set( "PSFSNRWeight", engine.PSFSNRWeight );
      P.set( "pedestal", engine.pedestal );

      P.set( "frameSelectionEnabled", engine.frameSelectionEnabled );
      P.set( "frameSelectionInteractive", engine.frameSelectionInteractive );

      // Export individual frame selection filter parameters
      // Use indexed parameters for Process Icon compatibility
      // (Parameters.set() doesn't accept dots in parameter names)
      if ( engine.frameSelectionDefaultConfig )
      {
         for ( let i = 0; i < engine.frameSelectionDefaultConfig.length; i++ )
         {
            let config = engine.frameSelectionDefaultConfig[ i ];

            parameters.setIndexed( "frameSelectionKey", i, config.key );
            parameters.setIndexed( "frameSelectionEnabled", i, config.enabled );
            parameters.setIndexed( "frameSelectionValue", i, config.value );
            parameters.setIndexed( "frameSelectionCompareMode", i, config.compareMode );

            if ( config.isCustomFormula && config.formula )
               parameters.setIndexed( "frameSelectionFormula", i, config.formula );
         }
      }

      P.set( "localNormalization", engine.localNormalization );
      P.set( "localNormalizationInteractiveMode", engine.localNormalizationInteractiveMode );
      P.set( "localNormalizationGenerateImages", engine.localNormalizationGenerateImages );
      P.set( "localNormalizationMethod", engine.localNormalizationMethod );
      P.set( "localNormalizationMaxIntegratedFrames", engine.localNormalizationMaxIntegratedFrames );
      P.set( "localNormalizationBestReferenceSelectionMethod", engine.localNormalizationBestReferenceSelectionMethod );
      P.set( "localNormalizationGridSize", engine.localNormalizationGridSize );
      P.set( "localNormalizationReferenceFrameGenerationMethod", engine.localNormalizationReferenceFrameGenerationMethod );
      P.set( "localNormalizationPsfType", engine.localNormalizationPsfType );
      P.set( "localNormalizationPsfGrowth", engine.localNormalizationPsfGrowth );
      P.set( "localNormalizationPsfMaxStars", engine.localNormalizationPsfMaxStars );
      P.set( "localNormalizationPsfMinSNR", engine.localNormalizationPsfMinSNR );
      P.set( "localNormalizationPsfAllowClusteredSources", engine.localNormalizationPsfAllowClusteredSources );
      P.set( "localNormalizationLowClippingLevel", engine.localNormalizationLowClippingLevel );
      P.set( "localNormalizationHighClippingLevel", engine.localNormalizationHighClippingLevel );

      P.set( "integrate", engine.integrate );
      P.set( "autocrop", engine.autocrop );
      P.set( "autoIntegrationMode", engine.autoIntegrationMode );

      P.set( "recombineRGB", engine.recombineRGB );
      P.set( "debayerActiveChannelR", engine.debayerActiveChannelR );
      P.set( "debayerActiveChannelG", engine.debayerActiveChannelG );
      P.set( "debayerActiveChannelB", engine.debayerActiveChannelB );

      P.set( "usePipelineScript", engine.usePipelineScript );
      P.set( "pipelineScriptFile", engine.pipelineScriptFile );
      P.set( "usePipelineBuilderScript", engine.usePipelineBuilderScript );
      P.set( "pipelineBuilderScriptFile", engine.pipelineBuilderScriptFile );

      P.set( "enableCompactGUI", engine.enableCompactGUI );

      P.set( "keywords", WBPPUtils.toBase64UTF8( JSON.stringify( engine.keywords.list ) ) );

      P.set( "groups", WBPPUtils.toBase64UTF8( this.groupsToStringData() ) );
      P.set( BPP.Constants.CACHE_VERSION, WBPPUtils.toBase64UTF8( engine.executionCache.toString() ) );

      if ( toJSON )
         P.set( "testExecutionStatus", JSON.stringify( engine.executionStatus
            ||
            {} ) );

      if ( toJSON )
         return JSON.stringify( P, null, 2 );
      return undefined;
   }

   // ........................................................................

   exportTest( filePath )
   {
      let engine = this.engine;

      for ( let i = 0; i < engine.groupsManager.groups.length; ++i )
         if ( engine.groupsManager.groups[ i ].hasMaster )
            engine.groupsManager.groups[ i ].removeItem( 0 );

      let json = this.exportParameters( true /* toJson */ );
      File.writeTextFile( filePath, json );
   }

   // ........................................................................
   // Group B: Serialization and migration
   // ........................................................................

   groupsToStringData()
   {
      let engine = this.engine;

      // from version 2.1.3 manual groups matching overrides references
      // are replaced by the group ID before saving and restored once reloaded
      engine.groupsManager.groups.forEach( ( group ) =>
      {
         if ( group.overrideDark && group.overrideDark.id )
            group.overrideDark = group.overrideDark.id;
         if ( group.overrideFlat && group.overrideFlat.id )
            group.overrideFlat = group.overrideFlat.id;
      } );
      let stringData = JSON.stringify( engine.groupsManager.groups, null, 2 );
      this.relinkManualOverrides();
      // save files structure
      return stringData;
   }

   // ........................................................................

   /**
    * Decode the list of groups from a JSON string.
    *
    * @param {*} data
    */
   groupsFromStringData( data, version )
   {
      let engine = this.engine;

      try
      {
         let groupsData = JSON.parse( data );

         // save files structure
         if ( groupsData )
         {
            engine.removePurgedElements();
            this.migrateGroupsData( groupsData, version );
            this.relinkManualOverrides();
            engine.reconstructGroups();
         }
      }
      catch ( e )
      {
         console.noteln( e );
         console.noteln( "Error occurred while loading saved groups. Group list will be cleared." );
         engine.groupsManager.clear();
      }
   }

   // ........................................................................

   /**
    * Migrates old data versions to the current version
    *
    * @param {*} groupsData groups data to be migrated
    */
   migrateGroupsData( groupsData, version )
   {
      let engine = this.engine;

      // migration occurs with WBPP only
      if ( version == undefined || ( !engine.fastMode && WBPPUtils.versionLT( version, "2.5.0" ) ) )
      {
         // braking change: group ID changed (fixed)
         console.noteln( "WBPP v2.5.0 group data is not compatible with earlier versions (", version, "). All group properties will be reset to default values." );

         let fileItems = [];
         groupsData.forEach( group =>
         {
            if ( group.mode == BPP.GroupingMode.PRE )
               for ( let j = 0; j < group.fileItems.length; ++j )
                  fileItems.push( group.fileItems[ j ] );
         } );

         engine.groupsManager.clear();
         engine.groupsManager.clearCache();

         // re-add files one by one
         console.show();
         for ( let i = 0; i < fileItems.length; ++i )
         {
            // show progressing
            console.noteln( "reading [", i, "/", fileItems.length, "] ", fileItems[ i ].filePath );
            engine.addFile( fileItems[ i ].filePath, fileItems[ i ].imageType );
         }
         console.hide();
      }

      // Migrate 0-based BPP.ImageType to 1-based PJSR ImageType
      if ( WBPPUtils.versionLT( version, engine.fastMode ? "1.2.1" : "3.0.1" ) )
      {
         for ( let i = 0; i < groupsData.length; ++i )
         {
            if ( groupsData[ i ].imageType != undefined )
               groupsData[ i ].imageType = groupsData[ i ].imageType + 1;
            if ( groupsData[ i ].fileItems )
               for ( let j = 0; j < groupsData[ i ].fileItems.length; ++j )
                  if ( groupsData[ i ].fileItems[ j ].imageType != undefined )
                     groupsData[ i ].fileItems[ j ].imageType = groupsData[ i ].fileItems[ j ].imageType + 1;
         }
      }

      // Migrate the cosmetic correction data. ccData has been added to groups, it contains the information about the CCTemplate name which now is stored at the group root level.
      // We need to move this informatino inside the ccData structure.
      // Valid for
      // - WBPP lower than 2.7.4
      if ( !engine.fastMode && WBPPUtils.versionLT( version, "2.7.4" ) )
      {
         for ( let i = 0; i < groupsData.length; ++i )
            if ( groupsData[ i ].imageType == ImageType.Light )
            {
               let newGroup = new FrameGroup( ImageType.Light );
               groupsData[ i ].ccData = newGroup.ccData;
               groupsData[ i ].ccData.CCTemplate = groupsData[ i ].CCTemplate;
               if ( groupsData[ i ].ccData.CCTemplate )
                  groupsData[ i ].ccData.enabled = false;
            }
      }

      engine.groupsManager.groups = groupsData;
   }

   /**
    * Reconstruct the links between the groups that has been manually assigned.
    * When groups are saved, the links are replaced by the the group id string,
    * once reloaded these strings must be replaced by the link to the group.
    *
    * This function must be called when groups has been loaded, migrated and
    * finally assigned to the groups manager.
    */
   relinkManualOverrides()
   {
      let engine = this.engine;

      engine.groupsManager.groups.forEach( ( group ) =>
      {
         if ( typeof group.overrideDark == "string" )
            group.overrideDark = engine.groupsManager.getGroupByID( group.overrideDark );
         if ( typeof group.overrideFlat == "string" )
            group.overrideFlat = engine.groupsManager.getGroupByID( group.overrideFlat );
      } );
   }

   // ........................................................................

   migrateKeywords( keywords, version )
   {
      let migrated = keywords;

      // ---------------------------
      // no keywords are suppored before version [2.0.2]
      if ( version == undefined )
      {
         return [];
      }

      return keywords;
   }

   // ........................................................................

   migrateFrom( dataVersion )
   {
      let engine = this.engine;

      if ( dataVersion == undefined || typeof dataVersion != typeof "" )
         dataVersion = "0.0.0";

      // migration versions
      let migrationVersions = [
      {
         version: "2.4.0", // migrate from versions < 2.4.0
         migration: () =>
         {
            // PSF power has been replaced by PSFSNR, set it to PSFSignal in case
            if ( engine.subframesWeightsMethod == undefined || engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.PSFSNR )
            {
               if ( engine.subframesWeightsMethod )
                  console.noteln( "* The weighting method PSF Power Weight has been removed and will be replaced by PSF Signal Weight" );
               engine.subframesWeightsMethod = BPP.SubframeWeightsMethod.PSFSignal;
            }
            // Rejection methods list has been shortened, map unavailable rejection methods to auto
            for ( let i = 0; i < 4; ++i )
            {
               // index correspond to auto if the rejection method is not listed
               let index = engine.rejectionIndex( engine.rejection[ i ] )
               engine.rejection[ i ] = engine.rejectionFromIndex( index )
            }
         }
      },
      {
         version: "2.4.1", // migrate from versions < 2.4.1
         migration: () =>
         {
            // PSFScaleSNR has been introduced after PSFSNR, update the old enumeration
            if ( engine.subframesWeightsMethod == undefined || engine.subframesWeightsMethod > BPP.SubframeWeightsMethod.PSFSNR )
               engine.subframesWeightsMethod = engine.subframesWeightsMethod + 1;
         }
      },
      {
         version: "2.4.3", // migrate from versions < 2.4.3
         migration: () =>
         {
            // New StarDetector engine V2 in core 1.8.9-1: reset star detection parameters to default values.
            engine.sensitivity = BPP.Defaults.saSensitivity;
            engine.peakResponse = BPP.Defaults.saPeakResponse;
            engine.maxStarDistortion = BPP.Defaults.saMaxStarDistortion;
         }
      },
      {
         version: "2.5.0", // migrate from versions < 2.5.0
         migration: () =>
         {
            // fix the issue with the LN max stars out of range (set the default value if OOR)
            if ( engine.localNormalizationPsfMaxStars > BPP.Defaults.localnormalizationPsfMaxStars
               || engine.localNormalizationPsfMaxStars < BPP.Defaults.localnormalizationPsfMinStars )
               engine.localNormalizationPsfMaxStars = BPP.Defaults.localnormalizationPsfMaxStars;
            // we always clear the cache when new version is installed
            engine.executionCache.reset();
         }
      },
      {
         version: "2.6.2", // migrate from version < 2.6.2
         migration: () =>
         {
            // grid size minimum value is 3
            engine.localNormalizationGridSize = Math.max( 3, engine.localNormalizationGridSize );
         }

      } ];

      // perform the migrations (WBPP only)
      for ( let i = 0; i < migrationVersions.length; ++i )
         if ( !engine.fastMode && WBPPUtils.versionLT( dataVersion, migrationVersions[ i ].version ) )
         {
            console.noteln( "* Migrating data from WBPP v", dataVersion, " to v", migrationVersions[ i ].version );
            // perform the migration
            migrationVersions[ i ].migration();
            dataVersion = migrationVersions[ i ].version;
         }
   }

   // ........................................................................
   // Group D: Configuration application
   // ........................................................................

   applyPreset( preset )
   {
      let engine = this.engine;

      switch ( preset )
      {
         case BPP.Presets.BEST_QUALITY:
            // enable and configure local normalization
            engine.localNormalization = true;
            engine.localNormalizationPsfType = LocalNormalization.PSFType_Auto;
            engine.localNormalizationPsfMaxStars = BPP.Defaults.localnormalizationPsfMaxStars;
            break;
         case BPP.Presets.MID:
            engine.localNormalization = true;
            engine.localNormalizationPsfType = LocalNormalization.PSFType_Moffat4;
            engine.localNormalizationPsfMaxStars = 500;
            break;
         case BPP.Presets.FAST:
            engine.localNormalization = false;
            break;
      }
   }

   // ........................................................................

   applyCFASettings( imageType, isCFA, CFAPattern, debayerMethod )
   {
      let engine = this.engine;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == imageType )
         {
            groups[ i ].isCFA = isCFA;
            groups[ i ].CFAPattern = CFAPattern;
            groups[ i ].debayerMethod = debayerMethod;
         }
   }

   // ........................................................................

   /**
    * Apply the provided output pedestal value to the pre-processing light frame groups.
    *
    * @param {Float} limit the output pedestal limit
    */
   applyOutputPedestalLimit( mode, pedestal, limit )
   {
      let engine = this.engine;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == ImageType.Light )
         {
            groups[ i ].lightOutputPedestalMode = mode;
            groups[ i ].lightOutputPedestal = pedestal;
            groups[ i ].lightOutputPedestalLimit = limit;
         }
   }

   // ........................................................................

   /**
    * Apply the provided Cosmetic Correction template icon to all pre-processing light frame groups.
    *
    * @param {String} templateIconName CosmeticCorrection template icon
    */
   applyCCData( ccData )
   {
      let engine = this.engine;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      for ( let i = 0; i < groups.length; ++i )
         if ( groups[ i ].imageType == ImageType.Light )
            groups[ i ].setCcData( ccData );
   }

   // ........................................................................

   /**
    * Apply the drizzle configuration of the given group to all post-calibration groups
    *
    * @param {String} referenceGroup The group containing the drizzle data to be
    *                                applied to all groups
    */
   applyDrizzleConfiguration( referenceGroup )
   {
      let engine = this.engine;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );

      for ( let i = 0; i < groups.length; ++i )
      {
         // skip virtual groups since they are
         groups[ i ].setDrizzleData( referenceGroup.drizzleData )
      }
   }

   // ........................................................................

   /**
    * Apply the fast integration configuration of the given group to all post-calibration groups
    *
    * @param {String} referenceGroup The group containing the fast integration data to be
    *                                applied to all groups
    */
   applyFastIntegrationConfiguration( referenceGroup )
   {
      let engine = this.engine;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );

      for ( let i = 0; i < groups.length; ++i )
      {
         // skip virtual groups
         if ( !groups[ i ].isVirtual() )
            groups[ i ].setFastIntegrationData( referenceGroup.fastIntegrationData )
      }
   }
};

// ----------------------------------------------------------------------------

/**
 * Sets the WBPP's engine default parameters.
 *
 */
function setDefaultParameters()
{
   // General options
   this.detectMasterIncludingFullPath = BPP.Defaults.masterDetectionUsesFullPath;
   this.smartNamingOverride = BPP.Defaults.smartNamingOverride;
   this.saveFrameGroups = BPP.Defaults.saveFrameGroups;
   this.outputDirectory = BPP.Defaults.outputDirectory;
   this.fitsCoordinateConvention = BPP.Defaults.fitsCoordinateConvention;
   this.generateRejectionMaps = engine.fastMode ? false : BPP.Defaults.generateRejectionMaps;
   this.preserveWhiteBalance = BPP.Defaults.preserveWhiteBalance;
   this.groupingKeywordsEnabled = BPP.Defaults.groupingKeywordsActive;
   this.showAstrometricInfo = BPP.Defaults.showAstrometricInfo;

   // Calibration parameters
   this.darkOptimizationThreshold = 0; // ### deprecated - retained for compatibility
   this.darkOptimizationLow = BPP.Defaults.darkOptimizationLow; // in sigma units from the central value
   this.darkOptimizationWindow = BPP.Defaults.darkOptimizationWindow;
   this.darkExposureTolerance = BPP.Defaults.darkExposureTolerance; // in seconds

   // Image integration parameters
   for ( let imageType = ImageType.Bias; imageType <= ImageType.Light; ++imageType )
      this.defaults.imageIntegration( imageType );

   // Overscan
   this.overscan.enabled = false;
   this.defaults.overscan();

   this.minWeight = BPP.Defaults.minWeight;

   // Light
   this.lightExposureTolerance = BPP.Defaults.lightExposureTolerance; // in seconds
   this.lightExposureTolerancePost = BPP.Defaults.lightExposureTolerancePost; // in seconds
   this.imageRegistration = BPP.Defaults.imageRegistration;

   // Linear Pattern Subtraction
   this.linearPatternSubtraction = BPP.Defaults.linearPatternSubtraction;
   this.linearPatternSubtractionRejectionLimit = BPP.Defaults.linearPatternSubtractionSigma;
   this.linearPatternSubtractionMode = BPP.Defaults.linearPatternSubtractionMode;

   // Subframe weights
   this.subframeWeightingEnabled = BPP.Defaults.subframeweightingEnabled;
   this.subframesWeightsMethod = BPP.Defaults.subframeweightingMethod;
   this.defaults.customFormulaWeights();

   // Frames selection
   this.frameSelectionEnabled = BPP.Defaults.frameselectionEnabled;
   this.frameSelectionInteractive = BPP.Defaults.frameselectionInteractive;
   this.defaults.frameSelectionFilters();

   // Image Solver
   this.platesolve = BPP.Defaults.saPlatesolve;
   this.platesolveFallbackManual = engine.fastMode ? false : BPP.Defaults.saPlateSolveFallbackManual;
   this.defaults.imageSolver();

   // Local normalization
   this.defaults.localNormalization();

   // Image registration
   this.referenceImage = "";
   this.bestFrameReferenceKeyword = "";
   this.bestFrameReferenceMethod = BPP.Defaults.bestReferenceMethod;
   this.debayerOutputMethod = BPP.Defaults.debayerOutputMethod;
   this.defaults.imageRegistration();

   // post-calibration
   this.debayerActiveChannelR = true;
   this.debayerActiveChannelG = true;
   this.debayerActiveChannelB = true;
   this.recombineRGB = BPP.Defaults.recombineRgb;

   // pipeline scripting
   this.usePipelineScript = false;
   this.pipelineScriptFile = "";
   this.usePipelineBuilderScript = false;
   this.pipelineBuilderScriptFile = "";

   // FBPP settings
   if ( engine.fastMode )
   {
      // disabled
      this.autocrop = false;
      this.autoIntegrationMode = false;
      this.linearPatternSubtraction = false;
      // enabled (used for "load in WBPP" feautre)
      this.subframeWeightingEnabled = true;
      this.localNormalization = true;
      this.imageRegistration = true;
      this.imageIntegration = true;
   }

   // tracking of groups with auto-enabled fast integration
   this.resetAutomaticFastImagingModeGroups();

   // GUI
   this.enableCompactGUI = false;
   this.GUIBiasPageOverscanControlCollapsed = true;
   this.GUIBiasPageImageIntegrationControlCollapsed = true;
   this.GUIDarkPageImageIntegrationControlCollapsed = true;
   this.GUIFlatPageImageIntegrationControlCollapsed = true;
   this.GUILightPageLPSControlCollapsed = true;
   this.GUILightPageSubframeWeightingControlCollapsed = true;
   this.GUILightPageFrameSelectionControlCollapsed = true;
   this.GUILightPageRegistrationControlCollapsed = true;
   this.GUIPlatesolveControlCollapsed = true;
   this.GUILightPageNormalizationControlCollapsed = true;
   this.GUILightPageIntegrationControlCollapsed = true;

   this.GUIPresetsCollapsed = true;
   this.GUIKeywordsCollapsed = true;
   this.GUIGlobalOptionsCollapsed = true;
   this.GUIReferenceFrameCollapsed = true;
   this.GUIOutputDirCollapsed = true;

   this.GUIGroupOverscanSettingsCollapsed = true;
   this.GUIGroupCalibrationSettingsCollapsed = true;
   this.GUIGroupPedestalSettingsCollapsed = true;
   this.GUIGroupCCSettingsCollapsed = true;
   this.GUIGroupDebayerSettingsCollapsed = true;

   this.globalOptionsHidden = false;

   this.integrate = BPP.Defaults.integrate;
   this.autocrop = BPP.Defaults.autocrop;
   this.autoIntegrationMode = BPP.Defaults.autoIntegrationMode;

   this.viewMode = BPP.GroupingMode.PRE;

   this.keywords = new Keywords();

   // automation mode is disabled by default
   this.automationMode = false;

   // simple mode is disabled by default
   this.simple_mode = BPP.Defaults.simpleMode;
}

// ----------------------------------------------------------------------------
// EOF BPP-ParametersManager.js - Released 2026-05-10T11:05:00Z
