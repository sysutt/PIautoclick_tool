// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-SettingsManager.js - Released 2026-05-10T11:05:00Z
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

var SettingsManager = class
{
   constructor( parametersManager )
   {
      this.parametersManager = parametersManager;
      this.engine = parametersManager.engine;
   }

   // ........................................................................
   // Settings persistence (read/write from PixInsight Settings API)
   // ........................................................................

   /**
    * Load the persisted WBPP settings.
    *
    * @param {boolean} skipMigration - if true the migration will be skipped
    * @returns
    */
   loadSettings( skipMigration )
   {
      let engine = this.engine;

      function load( key, type )
      {
         return Settings.read( engine.loadSettingsKeyBase + key, type );
      }

      function loadIndexed( key, index, type )
      {
         return load( key + '_' + index.toString(), type );
      }

      let o;

      let dataVersion = undefined;
      if ( ( o = load( "VERSION", DataType.UTF8String ) ) != null )
         dataVersion = o;

      // Threshold version from which keywords/groups are persisted as base64.
      // WBPP and FBPP have independent version numbers, so the threshold differs.
      const base64Since = engine.fastMode ? "1.2.1" : "3.0.1";

      if ( ( o = load( "outputDirectory", DataType.UTF8String ) ) != null )
      {
         // from version 2.50 and above we use base64 representation to handle non utf8 characters
         if ( !engine.loadInWBPP && ( dataVersion == undefined || ( !engine.fastMode && WBPPUtils.versionLT( dataVersion, "2.5.0" ) ) ) )
            engine.outputDirectory = o;
         else
         {
            try
            {
               engine.outputDirectory = WBPPUtils.fromBase64UTF8( o );
            }
            catch ( e )
            {
               engine.outputDirectory = "";
            }
         }
      }

      if ( ( o = load( "saveFrameGroups", DataType.Boolean ) ) != null )
         engine.saveFrameGroups = o;
      if ( ( o = load( "smartNamingOverride", DataType.Boolean ) ) != null )
         engine.smartNamingOverride = o;
      if ( ( o = load( "fitsCoordinateConvention", DataType.Int32 ) ) != null )
         engine.fitsCoordinateConvention = o;
      if ( ( o = load( "detectMasterIncludingFullPath", DataType.Boolean ) ) != null )
         engine.detectMasterIncludingFullPath = o;
      if ( ( o = load( "generateRejectionMaps", DataType.Boolean ) ) != null )
         engine.generateRejectionMaps = o;
      if ( ( o = load( "preserveWhiteBalance", DataType.Boolean ) ) != null )
         engine.preserveWhiteBalance = o;
      if ( ( o = load( "groupingKeywordsEnabled", DataType.Boolean ) ) != null )
         engine.groupingKeywordsEnabled = o;
      if ( ( o = load( "showAstrometricInfo", DataType.Boolean ) ) != null )
         engine.showAstrometricInfo = o;

      if ( ( o = load( "darkOptimizationThreshold", DataType.Float ) ) != null )
         engine.darkOptimizationThreshold = o;
      if ( ( o = load( "darkOptimizationLow", DataType.Float ) ) != null )
         engine.darkOptimizationLow = o;
      if ( ( o = load( "darkExposureTolerance", DataType.Float ) ) != null )
         engine.darkExposureTolerance = o;
      if ( ( o = load( "lightExposureTolerance", DataType.Float ) ) != null )
         engine.lightExposureTolerance = o;
      if ( ( o = load( "lightExposureTolerancePost", DataType.Float ) ) != null )
         engine.lightExposureTolerancePost = o;

      if ( ( o = load( "overscanEnabled", DataType.Boolean ) ) != null )
         engine.overscan.enabled = o;
      for ( let i = 0; i < 4; ++i )
      {
         if ( ( o = loadIndexed( "overscanRegionEnabled", i, DataType.Boolean ) ) != null )
            engine.overscan.overscan[ i ].enabled = o;
         if ( ( o = loadIndexed( "overscanSourceX0", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].sourceRect.x0 = o;
         if ( ( o = loadIndexed( "overscanSourceY0", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].sourceRect.y0 = o;
         if ( ( o = loadIndexed( "overscanSourceX1", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].sourceRect.x1 = o;
         if ( ( o = loadIndexed( "overscanSourceY1", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].sourceRect.y1 = o;
         if ( ( o = loadIndexed( "overscanTargetX0", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].targetRect.x0 = o;
         if ( ( o = loadIndexed( "overscanTargetY0", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].targetRect.y0 = o;
         if ( ( o = loadIndexed( "overscanTargetX1", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].targetRect.x1 = o;
         if ( ( o = loadIndexed( "overscanTargetY1", i, DataType.Int32 ) ) != null )
            engine.overscan.overscan[ i ].targetRect.y1 = o;
      }
      if ( ( o = load( "overscanImageX0", DataType.Int32 ) ) != null )
         engine.overscan.imageRect.x0 = o;
      if ( ( o = load( "overscanImageY0", DataType.Int32 ) ) != null )
         engine.overscan.imageRect.y0 = o;
      if ( ( o = load( "overscanImageX1", DataType.Int32 ) ) != null )
         engine.overscan.imageRect.x1 = o;
      if ( ( o = load( "overscanImageY1", DataType.Int32 ) ) != null )
         engine.overscan.imageRect.y1 = o;

      if ( ( o = load( "minWeight", DataType.Float ) ) != null )
         engine.minWeight = o;

      for ( let i = 0; i < 4; ++i )
      {
         if ( ( o = loadIndexed( "combination", i, DataType.Int32 ) ) != null )
            engine.combination[ i ] = o;
         if ( ( o = loadIndexed( "rejection", i, DataType.Int32 ) ) != null )
            engine.rejection[ i ] = o;
         // compatibility from PI 1.8.7 and above
         if ( engine.rejection[ i ] == ImageIntegration.CCDClip )
            engine.rejection[ i ] = BPP.REJECTION_AUTO;
         if ( ( o = loadIndexed( "percentileLow", i, DataType.Float ) ) != null )
            engine.percentileLow[ i ] = o;
         if ( ( o = loadIndexed( "percentileHigh", i, DataType.Float ) ) != null )
            engine.percentileHigh[ i ] = o;
         if ( ( o = loadIndexed( "sigmaLow", i, DataType.Float ) ) != null )
            engine.sigmaLow[ i ] = o;
         if ( ( o = loadIndexed( "sigmaHigh", i, DataType.Float ) ) != null )
            engine.sigmaHigh[ i ] = o;
         if ( ( o = loadIndexed( "linearFitLow", i, DataType.Float ) ) != null )
            engine.linearFitLow[ i ] = o;
         if ( ( o = loadIndexed( "linearFitHigh", i, DataType.Float ) ) != null )
            engine.linearFitHigh[ i ] = o;
         if ( ( o = loadIndexed( "ESD_Outliers", i, DataType.Float ) ) != null )
            engine.ESD_Outliers[ i ] = o;
         if ( ( o = loadIndexed( "ESD_Significance", i, DataType.Float ) ) != null )
            engine.ESD_Significance[ i ] = o;
         if ( ( o = loadIndexed( "RCR_Limit", i, DataType.Float ) ) != null )
            engine.RCR_Limit[ i ] = o;
      }

      if ( ( o = load( "flatsLargeScaleRejection", DataType.Boolean ) ) != null )
         engine.flatsLargeScaleRejection = o;
      if ( ( o = load( "flatsLargeScaleRejectionLayers", DataType.Int32 ) ) != null )
         engine.flatsLargeScaleRejectionLayers = o;
      if ( ( o = load( "flatsLargeScaleRejectionGrowth", DataType.Int32 ) ) != null )
         engine.flatsLargeScaleRejectionGrowth = o;
      if ( ( o = load( "lightsLargeScaleRejectionHigh", DataType.Boolean ) ) != null )
         engine.lightsLargeScaleRejectionHigh = o;
      if ( ( o = load( "lightsLargeScaleRejectionLayersHigh", DataType.Int32 ) ) != null )
         engine.lightsLargeScaleRejectionLayersHigh = o;
      if ( ( o = load( "lightsLargeScaleRejectionGrowthHigh", DataType.Int32 ) ) != null )
         engine.lightsLargeScaleRejectionGrowthHigh = o;
      if ( ( o = load( "lightsLargeScaleRejectionLow", DataType.Boolean ) ) != null )
         engine.lightsLargeScaleRejectionLow = o;
      if ( ( o = load( "lightsLargeScaleRejectionLayersLow", DataType.Int32 ) ) != null )
         engine.lightsLargeScaleRejectionLayersLow = o;
      if ( ( o = load( "lightsLargeScaleRejectionGrowthLow", DataType.Int32 ) ) != null )
         engine.lightsLargeScaleRejectionGrowthLow = o;
      if ( ( o = load( "imageRegistration", DataType.Boolean ) ) != null )
         engine.imageRegistration = o;

      if ( ( o = load( "linearPatternSubtraction", DataType.Boolean ) ) != null )
         engine.linearPatternSubtraction = o;
      if ( ( o = load( "linearPatternSubtractionRejectionLimit", DataType.Int32 ) ) != null )
         engine.linearPatternSubtractionRejectionLimit = o;
      if ( ( o = load( "linearPatternSubtractionMode", DataType.Int32 ) ) != null )
         engine.linearPatternSubtractionMode = o;

      if ( ( o = load( "subframeWeightingEnabled", DataType.Boolean ) ) != null )
         engine.subframeWeightingEnabled = o;
      if ( ( o = load( "subframeWeightingPreset", DataType.Int32 ) ) != null )
         engine.subframeWeightingPreset = o;
      if ( ( o = load( "frameSelectionEnabled", DataType.Boolean ) ) != null )
         engine.frameSelectionEnabled = o;
      if ( ( o = load( "frameSelectionInteractive", DataType.Boolean ) ) != null )
         engine.frameSelectionInteractive = o;

      // Load individual frame selection filter parameters (indexed format)
      {
         let frameSelectionFilterKeys = [ "FWHM", "eccentricity", "PSFSignalWeight", "median", "numberOfStars", "custom" ];
         let hasAnyFilterParam = false;
         let filterConfigs = [];

         for ( let i = 0; i < frameSelectionFilterKeys.length; i++ )
         {
            let config = {
               enabled: false,
               key: "",
               value: 0,
               compareMode: 0
            };

            if ( ( o = loadIndexed( "frameSelectionKey", i, DataType.UTF8String ) ) != null )
            {
               config.key = o;
               hasAnyFilterParam = true;
            }
            else
               break;

            if ( ( o = loadIndexed( "frameSelectionEnabled", i, DataType.Boolean ) ) != null )
               config.enabled = o;
            if ( ( o = loadIndexed( "frameSelectionValue", i, DataType.Float ) ) != null )
               config.value = o;
            if ( ( o = loadIndexed( "frameSelectionCompareMode", i, DataType.Int32 ) ) != null )
               config.compareMode = o;

            if ( config.key === "custom" )
            {
               config.isCustomFormula = true;
               if ( ( o = loadIndexed( "frameSelectionFormula", i, DataType.UTF8String ) ) != null )
                  config.formula = o;
               else
                  config.formula = "";
            }

            filterConfigs.push( config );
         }

         if ( hasAnyFilterParam )
            engine.frameSelectionDefaultConfig = filterConfigs;
      }

      if ( ( o = load( "subframesWeightsMethod", DataType.Int32 ) ) != null )
         engine.subframesWeightsMethod = o;

      if ( ( o = load( "FWHMWeight", DataType.Int32 ) ) != null )
         engine.FWHMWeight = o;
      if ( ( o = load( "eccentricityWeight", DataType.Int32 ) ) != null )
         engine.eccentricityWeight = o;
      if ( ( o = load( "SNRWeight", DataType.Int32 ) ) != null )
         engine.SNRWeight = o;
      if ( ( o = load( "starsWeight", DataType.Int32 ) ) != null )
         engine.starsWeight = o;
      if ( ( o = load( "PSFSignalWeight", DataType.Int32 ) ) != null )
         engine.PSFSignalWeight = o;
      if ( ( o = load( "PSFSNRWeight", DataType.Int32 ) ) != null )
         engine.PSFSNRWeight = o;
      if ( ( o = load( "pedestal", DataType.Int32 ) ) != null )
         engine.pedestal = o;

      if ( ( o = load( "localNormalization", DataType.Boolean ) ) != null )
         engine.localNormalization = o;
      if ( ( o = load( "localNormalizationInteractiveMode", DataType.Boolean ) ) != null )
         engine.localNormalizationInteractiveMode = o;
      if ( ( o = load( "localNormalizationGenerateImages", DataType.Boolean ) ) != null )
         engine.localNormalizationGenerateImages = o;
      if ( ( o = load( "localNormalizationMethod", DataType.Int32 ) ) != null )
         engine.localNormalizationMethod = o;
      if ( ( o = load( "localNormalizationMaxIntegratedFrames", DataType.Int32 ) ) != null )
         engine.localNormalizationMaxIntegratedFrames = o;
      if ( ( o = load( "localNormalizationBestReferenceSelectionMethod", DataType.Int32 ) ) != null )
         engine.localNormalizationBestReferenceSelectionMethod = o;
      if ( ( o = load( "localNormalizationGridSize", DataType.Int32 ) ) != null )
         engine.localNormalizationGridSize = o;
      if ( ( o = load( "localNormalizationReferenceFrameGenerationMethod", DataType.Int32 ) ) != null )
         engine.localNormalizationReferenceFrameGenerationMethod = o;
      if ( ( o = load( "localNormalizationPsfType", DataType.Int32 ) ) != null )
         engine.localNormalizationPsfType = o;
      if ( ( o = load( "localNormalizationPsfGrowth", DataType.Float ) ) != null )
         engine.localNormalizationPsfGrowth = o;
      if ( ( o = load( "localNormalizationPsfMaxStars", DataType.Int32 ) ) != null )
         engine.localNormalizationPsfMaxStars = o;
      if ( ( o = load( "localNormalizationPsfMinSNR", DataType.Float ) ) != null )
         engine.localNormalizationPsfMinSNR = o;
      if ( ( o = load( "localNormalizationPsfAllowClusteredSources", DataType.Boolean ) ) != null )
         engine.localNormalizationPsfAllowClusteredSources = o;
      if ( ( o = load( "localNormalizationLowClippingLevel", DataType.Float ) ) != null )
         engine.localNormalizationLowClippingLevel = o;
      if ( ( o = load( "localNormalizationHighClippingLevel", DataType.Float ) ) != null )
         engine.localNormalizationHighClippingLevel = o;
      if ( ( o = load( "reuseLastLNReferenceFrames", DataType.Boolean ) ) != null )
         engine.reuseLastLNReferenceFrames = o;

      if ( ( o = load( "platesolve", DataType.Boolean ) ) != null )
         engine.platesolve = o;
      if ( ( o = load( "platesolveFallbackManual", DataType.Boolean ) ) != null )
         engine.platesolveFallbackManual = o;
      if ( ( o = load( "imageSolverRa", DataType.Double ) ) != null )
         engine.imageSolverRa = o;
      if ( ( o = load( "imageSolverDec", DataType.Double ) ) != null )
         engine.imageSolverDec = o;
      if ( ( o = load( "imageSolverObservationTime", DataType.Double ) ) != null )
         engine.imageSolverObservationTime = o;
      if ( ( o = load( "imageSolverFocalLength", DataType.Float ) ) != null )
         engine.imageSolverFocalLength = o;
      if ( ( o = load( "imageSolverPixelSize", DataType.Float ) ) != null )
         engine.imageSolverPixelSize = o;
      if ( ( o = load( "imageSolverForceDefaults", DataType.Boolean ) ) != null )
         engine.imageSolverForceDefaults = o;

      if ( ( o = load( "pixelInterpolation", DataType.Int32 ) ) != null )
         engine.pixelInterpolation = o;
      if ( ( o = load( "clampingThreshold", DataType.Float ) ) != null )
         engine.clampingThreshold = o;
      if ( ( o = load( "maxStars", DataType.Int32 ) ) != null )
         engine.maxStars = o;
      if ( ( o = load( "distortionCorrection", DataType.Boolean ) ) != null )
         engine.distortionCorrection = o;
      if ( ( o = load( "maxSplinePoints", DataType.Int32 ) ) != null )
         engine.maxSplinePoints = o;
      if ( ( o = load( "rigidTransformations", DataType.Boolean ) ) != null )
         engine.rigidTransformations = o;
      if ( ( o = load( "structureLayers", DataType.Int32 ) ) != null )
         engine.structureLayers = o;
      if ( ( o = load( "hotPixelFilterRadius", DataType.Int32 ) ) != null )
         engine.hotPixelFilterRadius = o;
      if ( ( o = load( "noiseReductionFilterRadius", DataType.Int32 ) ) != null )
         engine.noiseReductionFilterRadius = o;
      if ( ( o = load( "minStructureSize", DataType.Int32 ) ) != null )
         engine.minStructureSize = o;
      if ( ( o = load( "sensitivity", DataType.Float ) ) != null )
         engine.sensitivity = o;
      if ( ( o = load( "peakResponse", DataType.Float ) ) != null )
         engine.peakResponse = o;
      if ( ( o = load( "brightThreshold", DataType.Float ) ) != null )
         engine.brightThreshold = o;
      if ( ( o = load( "maxStarDistortion", DataType.Float ) ) != null )
         engine.maxStarDistortion = o;
      if ( ( o = load( "allowClusteredSources", DataType.Boolean ) ) != null )
         engine.allowClusteredSources = o;
      if ( ( o = load( "useTriangleSimilarity", DataType.Boolean ) ) != null )
         engine.useTriangleSimilarity = o;
      if ( ( o = load( "reuseLastReferenceFrames", DataType.Boolean ) ) != null )
         engine.reuseLastReferenceFrames = o;

      if ( ( o = load( "integrate", DataType.Boolean ) ) != null )
         engine.integrate = o;
      if ( ( o = load( "autocrop", DataType.Boolean ) ) != null )
         engine.autocrop = o;
      if ( ( o = load( "autoIntegrationMode", DataType.Boolean ) ) != null )
         engine.autoIntegrationMode = o;
      if ( ( o = load( "usePipelineScript", DataType.Boolean ) ) != null )
         engine.usePipelineScript = o;
      if ( ( o = load( "pipelineScriptFile", DataType.UTF8String ) ) != null )
         engine.pipelineScriptFile = o;

      if ( ( o = load( "usePipelineBuilderScript", DataType.Boolean ) ) != null )
         engine.usePipelineBuilderScript = o;
      if ( ( o = load( "pipelineBuilderScriptFile", DataType.UTF8String ) ) != null )
         engine.pipelineBuilderScriptFile = o;

      if ( ( o = load( "referenceImage", DataType.UTF8String ) ) != null )
         engine.referenceImage = o;
      if ( ( o = load( "bestFrameReferenceKeyword", DataType.UTF8String ) ) != null )
         engine.bestFrameReferenceKeyword = o;

      // migration from wbpp 2.7.8 and earlier
      if ( ( o = load( "bestFrameRefernceMethod", DataType.Int32 ) ) != null )
         engine.bestFrameReferenceMethod = o;
      if ( ( o = load( "bestFrameReferenceMethod", DataType.Int32 ) ) != null )
         engine.bestFrameReferenceMethod = o;


      if ( ( o = load( "debayerOutputMethod", DataType.Int32 ) ) != null )
         engine.debayerOutputMethod = o;
      if ( ( o = load( "recombineRGB", DataType.Boolean ) ) != null )
         engine.recombineRGB = o;
      if ( ( o = load( "debayerActiveChannelR", DataType.Boolean ) ) != null )
         engine.debayerActiveChannelR = o;
      if ( ( o = load( "debayerActiveChannelG", DataType.Boolean ) ) != null )
         engine.debayerActiveChannelG = o;
      if ( ( o = load( "debayerActiveChannelB", DataType.Boolean ) ) != null )
         engine.debayerActiveChannelB = o;

      if ( ( o = load( "enableCompactGUI", DataType.Boolean ) ) != null )
         engine.enableCompactGUI = o;

      if ( ( o = load( "keywords", DataType.UTF8String ) ) != null )
      {
         // from WBPP 3.0.1 / FBPP 1.2.1 keywords are base64-encoded with UTF-8
         let keywordsStr;
         if ( dataVersion != undefined && !WBPPUtils.versionLT( dataVersion, base64Since ) )
         {
            try { keywordsStr = WBPPUtils.fromBase64UTF8( o ); }
            catch ( e ) { keywordsStr = o; }
         }
         else
            keywordsStr = o;
         let keywords = JSON.parse( keywordsStr );
         engine.keywords.list = this.parametersManager.migrateKeywords( keywords, dataVersion );
      }
      if ( engine.saveFrameGroups )
      {
         if ( ( o = load( "groups", DataType.UTF8String ) ) != null )
         {
            // from WBPP 3.0.1 / FBPP 1.2.1 groups are base64-encoded with UTF-8
            let groupsStr;
            if ( dataVersion != undefined && !WBPPUtils.versionLT( dataVersion, base64Since ) )
            {
               try { groupsStr = WBPPUtils.fromBase64UTF8( o ); }
               catch ( e ) { groupsStr = o; }
            }
            else
               groupsStr = o;
            this.parametersManager.groupsFromStringData( groupsStr, dataVersion );
         }
         else if ( ( o = load( "frameGroups", DataType.UTF8String ) ) != null ) /* WBPP 2.0.2 */
            this.parametersManager.groupsFromStringData( o, dataVersion );
      }

      try
      {
         let cacheContent = "";

         // compatibility with cache until WBPP 2.5.10
         if ( ( o = load( "executionCache", DataType.UTF8String ) ) != null )
         {
            cacheContent = o;
         }

         if ( cacheContent.length == 0 )
         {
            let fname = WBPPUtils.cacheFName();
            cacheContent = File.readFile( fname ).toString();
         }
         if ( cacheContent.length > 0 )
         {
            // measure parsing performance
            let elapsed = new ElapsedTime;
            engine.executionCache.fromString( cacheContent );
            console.noteln( "* Parsed cache data in ", elapsed.text );
         }
      }
      catch ( e )
      {
         engine.executionCache.reset();
      }

      if ( dataVersion && !skipMigration )
         this.parametersManager.migrateFrom( dataVersion );
   }

   // ........................................................................

   /**
    * Persist the WBPP settings.
    *
    */
   saveSettings()
   {
      let engine = this.engine;

      function save( key, type, value )
      {
         try
         {
            Settings.write( engine.saveSettingsKeyBase + key, type, value );
         }
         catch ( e )
         {
            console.warningln( "** Warning: Unable to save [", key, "] for type ", type, " with value ", value );
         }
      }

      function saveIndexed( key, index, type, value )
      {
         try
         {
            save( key + '_' + index.toString(), type, value );
         }
         catch ( e )
         {
            console.warningln( "** Warning: Unable to save [", key, "] for type", type, " with value ", value, " at index ", index );
         }
      }

      // base64 encoding to handle non utf8 chars
      save( "outputDirectory", DataType.UTF8String, WBPPUtils.toBase64UTF8( engine.outputDirectory ) );

      save( "saveFrameGroups", DataType.Boolean, engine.saveFrameGroups );
      save( "smartNamingOverride", DataType.Boolean, engine.smartNamingOverride );
      save( "detectMasterIncludingFullPath", DataType.Boolean, engine.detectMasterIncludingFullPath );
      save( "fitsCoordinateConvention", DataType.Int32, engine.fitsCoordinateConvention );
      save( "generateRejectionMaps", DataType.Boolean, engine.generateRejectionMaps );
      save( "preserveWhiteBalance", DataType.Boolean, engine.preserveWhiteBalance );
      save( "groupingKeywordsEnabled", DataType.Boolean, engine.groupingKeywordsEnabled );
      save( "showAstrometricInfo", DataType.Boolean, engine.showAstrometricInfo );

      save( "darkOptimizationLow", DataType.Float, engine.darkOptimizationLow );
      save( "darkExposureTolerance", DataType.Float, engine.darkExposureTolerance );
      save( "lightExposureTolerance", DataType.Float, engine.lightExposureTolerance );
      save( "lightExposureTolerancePost", DataType.Float, engine.lightExposureTolerancePost );

      save( "overscanEnabled", DataType.Boolean, engine.overscan.enabled );
      for ( let i = 0; i < 4; ++i )
      {
         saveIndexed( "overscanRegionEnabled", i, DataType.Boolean, engine.overscan.overscan[ i ].enabled );
         saveIndexed( "overscanSourceX0", i, DataType.Int32, engine.overscan.overscan[ i ].sourceRect.x0 );
         saveIndexed( "overscanSourceY0", i, DataType.Int32, engine.overscan.overscan[ i ].sourceRect.y0 );
         saveIndexed( "overscanSourceX1", i, DataType.Int32, engine.overscan.overscan[ i ].sourceRect.x1 );
         saveIndexed( "overscanSourceY1", i, DataType.Int32, engine.overscan.overscan[ i ].sourceRect.y1 );
         saveIndexed( "overscanTargetX0", i, DataType.Int32, engine.overscan.overscan[ i ].targetRect.x0 );
         saveIndexed( "overscanTargetY0", i, DataType.Int32, engine.overscan.overscan[ i ].targetRect.y0 );
         saveIndexed( "overscanTargetX1", i, DataType.Int32, engine.overscan.overscan[ i ].targetRect.x1 );
         saveIndexed( "overscanTargetY1", i, DataType.Int32, engine.overscan.overscan[ i ].targetRect.y1 );
      }
      save( "overscanImageX0", DataType.Int32, engine.overscan.imageRect.x0 );
      save( "overscanImageY0", DataType.Int32, engine.overscan.imageRect.y0 );
      save( "overscanImageX1", DataType.Int32, engine.overscan.imageRect.x1 );
      save( "overscanImageY1", DataType.Int32, engine.overscan.imageRect.y1 );

      save( "minWeight", DataType.Float, engine.minWeight );

      for ( let i = 0; i < 4; ++i )
      {
         saveIndexed( "combination", i, DataType.Int32, engine.combination[ i ] );
         saveIndexed( "rejection", i, DataType.Int32, engine.rejection[ i ] );
         saveIndexed( "percentileLow", i, DataType.Float, engine.percentileLow[ i ] );
         saveIndexed( "percentileHigh", i, DataType.Float, engine.percentileHigh[ i ] );
         saveIndexed( "sigmaLow", i, DataType.Float, engine.sigmaLow[ i ] );
         saveIndexed( "sigmaHigh", i, DataType.Float, engine.sigmaHigh[ i ] );
         saveIndexed( "linearFitLow", i, DataType.Float, engine.linearFitLow[ i ] );
         saveIndexed( "linearFitHigh", i, DataType.Float, engine.linearFitHigh[ i ] );
         saveIndexed( "ESD_Outliers", i, DataType.Float, engine.ESD_Outliers[ i ] );
         saveIndexed( "ESD_Significance", i, DataType.Float, engine.ESD_Significance[ i ] );
         saveIndexed( "RCR_Limit", i, DataType.Float, engine.RCR_Limit[ i ] );
      }

      save( "flatsLargeScaleRejection", DataType.Boolean, engine.flatsLargeScaleRejection );
      save( "flatsLargeScaleRejectionLayers", DataType.Int32, engine.flatsLargeScaleRejectionLayers );
      save( "flatsLargeScaleRejectionGrowth", DataType.Int32, engine.flatsLargeScaleRejectionGrowth );
      save( "lightsLargeScaleRejectionHigh", DataType.Boolean, engine.lightsLargeScaleRejectionHigh );
      save( "lightsLargeScaleRejectionLayersHigh", DataType.Int32, engine.lightsLargeScaleRejectionLayersHigh );
      save( "lightsLargeScaleRejectionGrowthHigh", DataType.Int32, engine.lightsLargeScaleRejectionGrowthHigh );
      save( "lightsLargeScaleRejectionLow", DataType.Boolean, engine.lightsLargeScaleRejectionLow );
      save( "lightsLargeScaleRejectionLayersLow", DataType.Int32, engine.lightsLargeScaleRejectionLayersLow );
      save( "lightsLargeScaleRejectionGrowthLow", DataType.Int32, engine.lightsLargeScaleRejectionGrowthLow );
      save( "imageRegistration", DataType.Boolean, engine.imageRegistration );

      save( "platesolve", DataType.Boolean, engine.platesolve );
      save( "platesolveFallbackManual", DataType.Boolean, engine.platesolveFallbackManual );
      save( "imageSolverRa", DataType.Double, engine.imageSolverRa );
      save( "imageSolverDec", DataType.Double, engine.imageSolverDec );
      save( "imageSolverObservationTime", DataType.Double, engine.imageSolverObservationTime );
      save( "imageSolverFocalLength", DataType.Float, engine.imageSolverFocalLength );
      save( "imageSolverPixelSize", DataType.Float, engine.imageSolverPixelSize );
      save( "imageSolverForceDefaults", DataType.Boolean, engine.imageSolverForceDefaults );

      save( "pixelInterpolation", DataType.Int32, engine.pixelInterpolation );
      save( "clampingThreshold", DataType.Float, engine.clampingThreshold );
      save( "maxStars", DataType.Int32, engine.maxStars );
      save( "distortionCorrection", DataType.Boolean, engine.distortionCorrection );
      save( "maxSplinePoints", DataType.Int32, engine.maxSplinePoints );
      save( "rigidTransformations", DataType.Boolean, engine.rigidTransformations );

      save( "linearPatternSubtraction", DataType.Boolean, engine.linearPatternSubtraction );
      save( "linearPatternSubtractionRejectionLimit", DataType.Int32, engine.linearPatternSubtractionRejectionLimit );
      save( "linearPatternSubtractionMode", DataType.Int32, engine.linearPatternSubtractionMode );

      save( "subframeWeightingEnabled", DataType.Boolean, engine.subframeWeightingEnabled );
      save( "subframeWeightingPreset", DataType.Int32, engine.subframeWeightingPreset );
      save( "subframesWeightsMethod", DataType.Int32, engine.subframesWeightsMethod );
      save( "frameSelectionEnabled", DataType.Boolean, engine.frameSelectionEnabled );
      save( "frameSelectionInteractive", DataType.Boolean, engine.frameSelectionInteractive );

      // Save individual frame selection filter parameters
      // Use indexed format for consistency with Process Icon export
      for ( let i = 0; i < engine.frameSelectionDefaultConfig.length; i++ )
      {
         let config = engine.frameSelectionDefaultConfig[ i ];
         saveIndexed( "frameSelectionKey", i, DataType.UTF8String, config.key );
         saveIndexed( "frameSelectionEnabled", i, DataType.Boolean, config.enabled );
         saveIndexed( "frameSelectionValue", i, DataType.Float, config.value );
         saveIndexed( "frameSelectionCompareMode", i, DataType.Int32, config.compareMode );

         if ( config.isCustomFormula && config.formula !== undefined )
            saveIndexed( "frameSelectionFormula", i, DataType.UTF8String, config.formula );
      }

      save( "FWHMWeight", DataType.Int32, engine.FWHMWeight );
      save( "eccentricityWeight", DataType.Int32, engine.eccentricityWeight );
      save( "SNRWeight", DataType.Int32, engine.SNRWeight );
      save( "starsWeight", DataType.Int32, engine.starsWeight );
      save( "PSFSignalWeight", DataType.Int32, engine.PSFSignalWeight );
      save( "PSFSNRWeight", DataType.Int32, engine.PSFSNRWeight );
      save( "pedestal", DataType.Int32, engine.pedestal );

      save( "localNormalization", DataType.Boolean, engine.localNormalization );
      save( "localNormalizationInteractiveMode", DataType.Boolean, engine.localNormalizationInteractiveMode );
      save( "localNormalizationGenerateImages", DataType.Boolean, engine.localNormalizationGenerateImages );
      save( "localNormalizationMethod", DataType.Int32, engine.localNormalizationMethod );
      save( "localNormalizationMaxIntegratedFrames", DataType.Int32, engine.localNormalizationMaxIntegratedFrames );
      save( "localNormalizationBestReferenceSelectionMethod", DataType.Int32, engine.localNormalizationBestReferenceSelectionMethod );
      save( "localNormalizationGridSize", DataType.Int32, engine.localNormalizationGridSize );
      save( "localNormalizationReferenceFrameGenerationMethod", DataType.Int32, engine.localNormalizationReferenceFrameGenerationMethod );
      save( "localNormalizationPsfType", DataType.Int32, engine.localNormalizationPsfType );
      save( "localNormalizationPsfGrowth", DataType.Float, engine.localNormalizationPsfGrowth );
      save( "localNormalizationPsfMaxStars", DataType.Int32, engine.localNormalizationPsfMaxStars );
      save( "localNormalizationPsfMinSNR", DataType.Float, engine.localNormalizationPsfMinSNR );
      save( "localNormalizationPsfAllowClusteredSources", DataType.Boolean, engine.localNormalizationPsfAllowClusteredSources );
      save( "localNormalizationLowClippingLevel", DataType.Float, engine.localNormalizationLowClippingLevel );
      save( "localNormalizationHighClippingLevel", DataType.Float, engine.localNormalizationHighClippingLevel );
      save( "reuseLastLNReferenceFrames", DataType.Boolean, engine.reuseLastLNReferenceFrames );

      save( "structureLayers", DataType.Int32, engine.structureLayers );
      save( "hotPixelFilterRadius", DataType.Int32, engine.hotPixelFilterRadius );
      save( "noiseReductionFilterRadius", DataType.Int32, engine.noiseReductionFilterRadius );
      save( "minStructureSize", DataType.Int32, engine.minStructureSize );
      save( "sensitivity", DataType.Float, engine.sensitivity );
      save( "peakResponse", DataType.Float, engine.peakResponse );
      save( "brightThreshold", DataType.Float, engine.brightThreshold );
      save( "maxStarDistortion", DataType.Float, engine.maxStarDistortion );
      save( "allowClusteredSources", DataType.Boolean, engine.allowClusteredSources );
      save( "useTriangleSimilarity", DataType.Boolean, engine.useTriangleSimilarity );
      save( "reuseLastReferenceFrames", DataType.Boolean, engine.reuseLastReferenceFrames );

      save( "integrate", DataType.Boolean, engine.integrate );
      save( "autocrop", DataType.Boolean, engine.autocrop );
      save( "autoIntegrationMode", DataType.Boolean, engine.autoIntegrationMode );

      save( "usePipelineScript", DataType.Boolean, engine.usePipelineScript );
      save( "pipelineScriptFile", DataType.UTF8String, engine.pipelineScriptFile );
      save( "usePipelineBuilderScript", DataType.Boolean, engine.usePipelineBuilderScript );
      save( "pipelineBuilderScriptFile", DataType.UTF8String, engine.pipelineBuilderScriptFile );

      save( "referenceImage", DataType.UTF8String, engine.referenceImage );
      save( "bestFrameReferenceKeyword", DataType.UTF8String, engine.bestFrameReferenceKeyword );
      save( "bestFrameReferenceMethod", DataType.Int32, engine.bestFrameReferenceMethod );

      save( "debayerOutputMethod", DataType.Int32, engine.debayerOutputMethod );
      save( "recombineRGB", DataType.Boolean, engine.recombineRGB );
      save( "debayerActiveChannelR", DataType.Boolean, engine.debayerActiveChannelR );
      save( "debayerActiveChannelG", DataType.Boolean, engine.debayerActiveChannelG );
      save( "debayerActiveChannelB", DataType.Boolean, engine.debayerActiveChannelB );

      save( "enableCompactGUI", DataType.Boolean, engine.enableCompactGUI );

      save( "VERSION", DataType.UTF8String, engine.version );

      save( "keywords", DataType.UTF8String, WBPPUtils.toBase64UTF8( JSON.stringify( engine.keywords.list ) ) );

      if ( engine.saveFrameGroups )
         save( "groups", DataType.UTF8String, WBPPUtils.toBase64UTF8( this.parametersManager.groupsToStringData() ) );

      // The execution cache is saved in a dedicated configuration path. We save the current cache only if WBPP is not loaded from a process icon.
      // In fast mode we don't save the cache.
      save( "executionCache", DataType.UTF8String, "" );
      if ( !engine.cacheHasBeenLoadedFromAnInstance && !engine.fastMode )
      {
         let cacheContent = engine.executionCache.toString();
         // If the cache is too big, we don't save it
         if ( cacheContent.length > 1024 * 1024 * 5 )
         {
            let response = new MessageBox( "Large cache detected (" + WBPPUtils.readableSize( engine.executionCache.size(), 0 ) + "), do you want to purge it?", engine.title, StdIcon.Question, StdButton.Yes, StdButton.No ).execute();
            if ( response == StdButton.Yes )
            {
               engine.executionCache.reset();
               cacheContent = engine.executionCache.toString();
            }
         }
         let fname = WBPPUtils.cacheFName();
         if ( File.exists( fname ) )
            File.remove( fname );
         File.writeTextFile( fname, cacheContent );
      }
   }

   // ........................................................................
   // Running configuration persistence
   // ........................................................................

   /**
    * Saves the current running configuration to persistent storage.
    * This function stores the current state of the engine to allow recovery
    * in case of unexpected termination.
    */
   saveRunningConfiguration()
   {
      let engine = this.engine;

      // temporary save the parameters
      if ( !engine.automationMode )
      {
         let configJSON = this.parametersManager.exportParameters( true /* toJSON*/ );
         Settings.write( engine.saveSettingsKeyBase + "runningConfiguration", DataType.UTF16String, configJSON );
         Settings.write( engine.saveSettingsKeyBase + "runningConfiguration_VERSION", DataType.UTF16String, engine.version );
      }
   }

   /**
    * Checks if a previously saved running configuration is available.
    * This is used to detect if the previous execution was interrupted
    * unexpectedly (e.g., crash or forced termination).
    *
    * @returns {Boolean} True if a valid configuration from the same version exists
    */
   hasRunningConfiguration()
   {
      let engine = this.engine;

      let hasConfiguration = Settings.read( engine.loadSettingsKeyBase + "runningConfiguration", DataType.UTF16String );
      let version = Settings.read( engine.loadSettingsKeyBase + "runningConfiguration_VERSION", DataType.UTF16String );
      // only configurations from the current version will be restored
      if ( version != engine.version )
      {
         this.removeRunningConfiguration();
         return false;
      }
      return hasConfiguration != undefined;
   }

   /**
    * Restores the previously saved running configuration.
    * This function loads the saved state, updates all parameters,
    * rebuilds the engine state, and then removes the saved configuration.
    */
   restoreRunningConfiguration()
   {
      let engine = this.engine;

      if ( !this.hasRunningConfiguration() )
         return;

      let configJSON = Settings.read( engine.loadSettingsKeyBase + "runningConfiguration", DataType.UTF16String );
      if ( configJSON )
      {
         this.parametersManager.importParameters( configJSON );
         engine.rebuild();
      }
      this.removeRunningConfiguration();
   }

   /**
    * Removes any saved running configuration from persistent storage.
    * This is typically called after successful completion of processing
    * or after successfully restoring a configuration.
    */
   removeRunningConfiguration()
   {
      let engine = this.engine;

      Settings.remove( engine.saveSettingsKeyBase + "runningConfiguration" );
      Settings.remove( engine.saveSettingsKeyBase + "runningConfiguration_VERSION" );
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-SettingsManager.js - Released 2026-05-10T11:05:00Z
