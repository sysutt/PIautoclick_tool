// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Global.js - Released 2026-05-10T11:05:00Z
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

/*
 * BPP namespace — contains BPP-specific enums, constants, and defaults.
 *
 * Some platform constants (StdButton, StdIcon, StdCursor, DataType, MouseButton)
 * are provided by the V8 runtime as global objects.
 * Others (TextAlign, FontFamily) require #include of their .jsh headers
 * (done in BPP-Main.js).
 *
 * Uses `var` so re-inclusion across script runs in the same V8 context
 * simply re-creates BPP (no const re-declaration error).
 */

var BPP = {};

// -------------------------------------------------------------------------
// Version / identity (formerly in BPP-Defines.jsh)
// -------------------------------------------------------------------------

BPP.Version = {
   WBPP_ID:               "WeightedBatchPreprocessing",
   WBPP_TITLE:            "Weighted Batch Preprocessing",
   WBPP_SETTINGS_KEY_BASE: "WeightedBatchPreprocessing/",
   WBPP_VERSION:          "3.0.1",

   FBPP_ID:               "FastBatchPreprocessing",
   FBPP_TITLE:            "Fast Batch Preprocessing",
   FBPP_SETTINGS_KEY_BASE: "FastBatchPreprocessing/",
   FBPP_VERSION:          "1.2.1",

   SETTINGS_MODULE:       "BPP"
};

// -------------------------------------------------------------------------
// FITS keywords
// -------------------------------------------------------------------------

BPP.Keywords = {
   WEIGHT:                   "WBPPWGHT",
   MEASUREMENT_FWHM:         "WBPPFWHM",
   MEASUREMENT_ECCENTRICITY: "WBPPECC",
   MEASUREMENT_NOISE:        "WBPPNOIS",
   MEASUREMENT_SNRWEIGHT:    "WBPPSNRW",
   MEASUREMENT_STARS:        "WBPPSTAR",
   MEASUREMENT_PSFSIGNAL:    "WBPPPSFS",
   MEASUREMENT_PSFSNR:       "WBPPPSFSNR",
   MEASUREMENT_SCORE:        "WBPPSCOR",
   AUTOCROP:                 "WBPPCROP"
};

// -------------------------------------------------------------------------
// Formatting helpers and charsets
// -------------------------------------------------------------------------

BPP.Format = {
   SEPARATOR:                        '*'.repeat( 60 ),
   SEPARATOR2:                       '-'.repeat( 60 ),
   KEYWORD_VALUE_CHARSET:            "-():. a-zA-Z0-9",
   FOLDER_NAME_CHARSET:              "-_():. a-zA-Z0-9",
   StdDialogCode_GenerateScreenshots: 2
};

// -------------------------------------------------------------------------
// Numeric constants
// -------------------------------------------------------------------------

BPP.Constants = {
   MIN_EXPOSURE_TOLERANCE: 0.01,
   FLAT_DARK_TOLERANCE:    0.5,
   CACHE_VERSION:          "cache_v2"
};

// -------------------------------------------------------------------------
// Rejection auto sentinel (replaces ImageIntegration.prototype.auto = 999)
// -------------------------------------------------------------------------

BPP.REJECTION_AUTO = 999;


// Converts a native PJSR ImageType value (1-based) to a 0-based array index.
// ImageType.Bias(1)->0, ImageType.Dark(2)->1, ImageType.Flat(3)->2, ImageType.Light(4)->3
BPP.imageTypeIndex = function( imageType ) { return imageType - 1; };

// -------------------------------------------------------------------------
// Application-specific enums (formerly WBPPGroupingMode, etc.)
// -------------------------------------------------------------------------

BPP.GroupingMode = {
   PRE:  1,
   POST: 2
};

BPP.KeywordMode = {
   NONE:    0,
   PRE:     1,
   POST:    2,
   PREPOST: 3
};

BPP.FrameProcessingStep = {
   CALIBRATION:   0,
   LPS:           1,
   CC:            2,
   DEBAYER:       3,
   WRITE_WEIGHTS: 4,
   REGISTRATION:  5,
   NORMALIZATION: 6,
   INTEGRATION:   7
};

BPP.BestReferenceMethod = {
   MANUAL:       0,
   AUTO_SINGLE:  1,
   AUTO_KEYWORD: 2
};

BPP.DebayerOutputMode = {
   COMBINED:  0,
   SEPARATED: 1,
   BOTH:      2
};

BPP.SubframeWeightsMethod = {
   PSFSignal:   0,
   PSFSNR:      1,
   PSFScaleSNR: 2,
   SNREstimate: 3,
   FORMULA:     4
};

BPP.LocalNormalizationMethod = {
   PSFFlux:            0,
   MultiscaleAnalysis: 1
};

BPP.LocalNormalizationRefFrameMethod = {
   SINGLE_BEST:             0,
   INTEGRATION_BEST_FRAMES: 1
};

BPP.LocalNormalizationRefFrameMetric = {
   PSFSW:  0,
   PSFSNR: 1,
   MSTAR:  2,
   MEDIAN: 3,
   STARS:  4
};

BPP.MasterType = {
   MASTER_LIGHT: 0,
   DRIZZLE:      1,
   RECOMBINED:   2,
   NOptions:     3
};

BPP.MasterVariant = {
   REGULAR:  0,
   CROPPED:  1,
   NOptions: 2
};

BPP.Presets = {
   BEST_QUALITY: 1,
   MID:          2,
   FAST:         3
};

BPP.AssociatedChannel = {
   R:            "_R",
   G:            "_G",
   B:            "_B",
   COMBINED_RGB: "combined RGB",
   sorted:       [ "_R", "_G", "_B", "combined RGB" ]
};

BPP.FastIntegrationWeightScheme = {
   NONE:       0,
   SNR:        1,
   RESOLUTION: 2
};

BPP.PlateSolveItem = {
   FILE:                0,
   MASTER:              1,
   MASTER_DRIZZLE:      2,
   MASTER_CROP:         3,
   MASTER_DRIZZLE_CROP: 4
};

// -------------------------------------------------------------------------
// Default parameter values
// Assigned separately so that enum references (BPP.*) are valid.
// -------------------------------------------------------------------------

BPP.Defaults = {

   // General
   masterDetectionUsesFullPath:   true,
   generateRejectionMaps:         true,
   preserveWhiteBalance:          false,
   saveFrameGroups:               true,
   smartNamingOverride:           false,
   outputDirectory:               "",
   fitsCoordinateConvention:      0,
   groupingKeywordsActive:        true,
   showAstrometricInfo:           true,

   // Dark
   darkIncludeBias:               true,
   optimizeDarks:                 false,
   darkOptimizationLow:           3.0,
   darkOptimizationWindow:        0,
   darkExposureTolerance:         10,

   // Cosmetic correction
   ccEnabled:                     true,
   ccHighSigma:                   10,
   ccMaxDarkExposureDiff:         15,

   // Rejection
   rejectionMethod:               BPP.REJECTION_AUTO,
   largeScaleRejection:           false,
   largeScaleLayers:              2,
   largeScaleGrowth:              2,

   // Light
   minWeight:                     0.05,
   lightExposureTolerance:        2,
   lightExposureTolerancePost:    2,
   lightOutputPedestal:           0,
   imageRegistration:             true,

   // Linear pattern subtraction
   linearPatternSubtraction:      false,
   linearPatternSubtractionSigma: 5,
   linearPatternSubtractionMode:  1,

   // Cosmetic
   cosmeticCorrection:            false,

   // Debayer
   cfaPattern:                    Debayer.Auto,
   debayerMethod:                 Debayer.VNG,
   debayerOutputMethod:           BPP.DebayerOutputMode.COMBINED,

   // Subframe weighting
   subframeweightingEnabled:      true,
   subframeweightingPreset:       1,
   subframeweightingMethod:       BPP.SubframeWeightsMethod.PSFSignal,

   // Frame selection
   frameselectionEnabled:         false,
   frameselectionInteractive:     true,

   // Pedestal
   pedestalMode:                  ImageCalibration.OutputPedestal_Auto,
   pedestalLimit:                 0.0001,

   // Best reference
   bestReferenceMethod:           BPP.BestReferenceMethod.AUTO_SINGLE,

   // Subframe weighting parameters
   subframeweightingFwhmWeight:         5,
   subframeweightingEccentricityWeight: 10,
   subframeweightingSnrWeight:          20,
   subframeweightingStarsWeight:        0,
   subframeweightingPsfSignalWeight:    0,
   subframeweightingPsfSnrWeight:       0,
   subframeweightingPedestal:           65,

   // Star alignment
   saPlatesolve:                      true,
   saPlateSolveFallbackManual:        true,
   saPixelInterpolation:              StarAlignment.Auto,
   saClampingThreshold:               0.3,
   saMaxStars:                        0,
   saDistortionCorrection:            false,
   saMaxSplinePoints:                 4000,
   saRigidTransformations:            false,
   saStructureLayers:                 5,
   saHotPixelFilterRadius:            1,
   saMinStructureSize:                0,
   saNoiseReduction:                  0,
   saSensitivity:                     0.5,
   saPeakResponse:                    0.5,
   saBrightThreshold:                 3.0,
   saMaxStarDistortion:               0.6,
   saAllowClusteredSources:           false,
   saUseTriangleSimilarity:           false,
   saDefaultReuseLastReferenceFrames: false,

   // Image solver
   imageSolverRa:                 0,
   imageSolverDec:                0,
   imageSolverObservationTime:    2451545.0, // J2000.0
   imageSolverFocalLength:        750.0,
   imageSolverPixelSize:          5.4,
   imageSolverForceDefaults:      false,

   // Local normalization
   localnormalization:                    true,
   localnormalizationInteractiveMode:     false,
   localnormalizationGenerateImages:      false,
   localnormalizationMethod:              BPP.LocalNormalizationMethod.PSFFlux,
   localnormalizationBestReferenceMethod: BPP.LocalNormalizationRefFrameMetric.PSFSW,
   localnormalizationGridSize:            4,
   localnormalizationRefFrameMethod:      BPP.LocalNormalizationRefFrameMethod.INTEGRATION_BEST_FRAMES,
   localnormalizationPsfType:             LocalNormalization.PSFType_Auto,
   localnormalizationPsfGrowth:           1.0,
   localnormalizationPsfMaxStars:         24576,
   localnormalizationPsfMinStars:         256,
   localnormalizationPsfMinSnr:           40.0,
   localnormalizationMinIntegratedFrames: 3,
   localnormalizationMaxIntegratedFrames: 1024,
   localnormalizationIntegratedFrames:    20,
   localnormalizationPsfAllowClustered:   true,
   localnormalizationLowClippingLevel:    4.5e-5,
   localnormalizationHighClippingLevel:   0.85,
   localnormalizationReuseReferenceFrame: false,

   // Drizzle
   drizzleFast:                   true,
   drizzleScale:                  1,
   drizzleDropShrinkMono:         0.9,
   drizzleDropShrinkCfa:          1.0,
   drizzleFunction:               DrizzleIntegration.Kernel_Square,
   drizzleGridSize:               16,

   // Integration
   integrate:                     true,
   autocrop:                      true,
   autoIntegrationMode:           true,
   drizzleMaster:                 true,
   recombineRgb:                  false,
   autoFastIntegrationThreshold:  150,

   // Miscellaneous
   frameGroups:                   [],
   simpleMode:                    false,
   associatedId:                  "default"
};

// ----------------------------------------------------------------------------
// EOF BPP-Global.js - Released 2026-05-10T11:05:00Z
