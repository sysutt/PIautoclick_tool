// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Automation.js - Released 2026-05-10T11:05:00Z
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
 * Automation mode utilities for WBPP/FBPP.
 * This module provides command-line parameter parsing and automation support.
 */

// ----------------------------------------------------------------------------
// Indexed parameter definitions
// Each entry specifies [name, type] where type is "Boolean", "Integer", or "Real"
// ----------------------------------------------------------------------------

var AUTOMATION_INDEXED_PARAMS = [
   [ "overscanRegionEnabled", "Boolean" ],
   [ "overscanSourceX0", "Integer" ],
   [ "overscanSourceY0", "Integer" ],
   [ "overscanSourceX1", "Integer" ],
   [ "overscanSourceY1", "Integer" ],
   [ "overscanTargetX0", "Integer" ],
   [ "overscanTargetY0", "Integer" ],
   [ "overscanTargetX1", "Integer" ],
   [ "overscanTargetY1", "Integer" ],
   [ "combination", "Integer" ],
   [ "rejection", "Integer" ],
   [ "percentileLow", "Real" ],
   [ "percentileHigh", "Real" ],
   [ "sigmaLow", "Real" ],
   [ "sigmaHigh", "Real" ],
   [ "linearFitLow", "Real" ],
   [ "linearFitHigh", "Real" ],
   [ "ESD_Outliers", "Real" ],
   [ "ESD_Significance", "Real" ],
   [ "RCR_Limit", "Real" ]
];

// ----------------------------------------------------------------------------
// Detection functions
// ----------------------------------------------------------------------------

/**
 * Checks if the script is running in automation mode.
 * @returns {boolean} true if "automationMode=true" is given as command line argument.
 */
function runsInAutomationMode()
{
   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let items = Runtime.jsArguments[ i ].split( "=" );
      if ( items.length == 2 && items[ 0 ] == "automationMode" && items[ 1 ].toLowerCase() == "true" )
         return true;
   }
   return false;
}

/**
 * Gets the test file path from command line arguments.
 * @returns {string|false} the test file path if specified, false otherwise.
 */
function getTestFile()
{
   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let items = Runtime.jsArguments[ i ].split( "=" );
      if ( items.length == 2 && items[ 0 ] == "testFile" )
         return items[ 1 ];
   }
   return false;
}

// ----------------------------------------------------------------------------
// Parsing helper functions
// ----------------------------------------------------------------------------

/**
 * Parses the keywords parameter with custom syntax.
 * Syntax: "keywords=KEYWORD1;KEYWORD2 mode;KEYWORD3 mode"
 * Where mode is: pre (default), post, or prepost
 *
 * @param {string} value - The keywords parameter value
 * @param {object} engine - The WBPP engine instance
 */
function parseKeywordsParam( value, engine )
{
   let keywordItems = value.split( ";" );

   for ( let j = 0; j < keywordItems.length; j++ )
   {
      let mode = BPP.KeywordMode.PRE;
      let name;
      let keywordData = keywordItems[ j ].trim().split( " " );

      if ( keywordData[ 0 ].length == 0 )
         continue;
      else if ( keywordData.length == 1 )
         name = keywordData[ 0 ];
      else if ( keywordData.length == 2 )
      {
         name = keywordData[ 0 ];
         let modeStr = keywordData[ 1 ];
         if ( modeStr.toLowerCase() == "pre" )
            mode = BPP.KeywordMode.PRE;
         else if ( modeStr.toLowerCase() == "post" )
            mode = BPP.KeywordMode.POST;
         else if ( modeStr.toLowerCase() == "prepost" )
            mode = BPP.KeywordMode.PREPOST;
         else
         {
            console.warningln( "unknown mode [" + modeStr + "] for keyword [" + name + "]" );
            continue;
         }
      }
      else if ( keywordData.length > 2 )
      {
         console.warningln( "unexpected syntax for keyword: ", keywordData );
         continue;
      }

      engine.keywords.add( name, mode );
   }
}

/**
 * Attempts to parse an indexed parameter (e.g., combination_1, rejection_2).
 * These parameters are saved with setIndexed (one-based) and must be parsed accordingly.
 *
 * @param {string} paramName - The parameter name (e.g., "combination_1")
 * @param {string} paramValue - The parameter value as string
 * @returns {boolean} true if the parameter was recognized and parsed as indexed
 */
function parseIndexedParam( paramName, paramValue )
{
   for ( let j = 0; j < AUTOMATION_INDEXED_PARAMS.length; ++j )
   {
      let baseName = AUTOMATION_INDEXED_PARAMS[ j ][ 0 ];
      let paramType = AUTOMATION_INDEXED_PARAMS[ j ][ 1 ];

      // Check if parameter matches pattern: baseName_<digit>
      let regex = new RegExp( "^" + baseName + "_(\\d+)$" );
      let match = paramName.match( regex );

      if ( match )
      {
         // indexedId uses one-based indices (index + 1), so subtract 1 from parsed index
         let index = parseInt( match[ 1 ] ) - 1;

         // Parse value according to parameter type
         let value;
         switch ( paramType )
         {
            case "Boolean":
               value = paramValue === "true" || paramValue === "1";
               break;
            case "Integer":
               value = parseInt( paramValue );
               break;
            case "Real":
               value = parseFloat( paramValue );
               break;
            default:
               value = paramValue;
         }

         WBPPUtils.parameters.setIndexed( baseName, index, value );
         return true;
      }
   }
   return false;
}

/**
 * Parses the fileSearchRootPath parameter from command line arguments.
 * This parameter specifies an alternative directory to locate file items
 * when their original paths are unavailable.
 *
 * @param {object} engine - The WBPP engine instance
 */
function parseFileSearchRootPath( engine )
{
   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let pItems = Runtime.jsArguments[ i ].split( "=" );
      if ( pItems.length == 2 && pItems[ 0 ] == "fileSearchRootPath" )
      {
         engine.fileSearchRootPath = pItems[ 1 ];
         console.noteln( "fileSearchRootPath: ", engine.fileSearchRootPath );
         break;
      }
   }
}

/**
 * Parses test mode override parameters from command line arguments.
 * These parameters can override values from the test file.
 *
 * @param {object} engine - The WBPP engine instance
 * @returns {boolean} doPerform - Whether to perform the processing
 */
function parseTestModeOverrides( engine )
{
   let doPerform = true;

   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let pItems = Runtime.jsArguments[ i ].split( "=" );

      // output directory can be assigned arbitrarily
      if ( pItems.length == 2 && pItems[ 0 ] == "outputDir" )
      {
         console.noteln( "Test out dir: ", pItems[ 1 ] );
         cout( "\nTest out dir: " + pItems[ 1 ] );
         engine.outputDirectory = pItems[ 1 ];
      }
      else if ( pItems.length == 2 && pItems[ 0 ] == "usePipelineScript" )
      {
         // if load only then we don't use the pipeline script
         if ( engine.testLoadOnly )
         {
            console.noteln( "Pipeline script disabled as the test requires 'load only'" );
            cout( "\nPipeline script disabled as the test requires 'load only'" );
         }
         else
         {
            console.noteln( "Using pipeline script: ", pItems[ 1 ] );
            cout( "\nUsing pipeline script: " + pItems[ 1 ] );
            engine.usePipelineScript = pItems[ 1 ].toLowerCase() == "true";
         }
      }
      else if ( pItems.length == 2 && pItems[ 0 ] == "pipelineBuilderScriptFile" )
      {
         console.noteln( "Pipeline builder script file: ", pItems[ 1 ] );
         cout( "\nPipeline builder script file: " + pItems[ 1 ] );
         engine.pipelineBuilderScriptFile = pItems[ 1 ];
      }
      else if ( pItems.length == 2 && pItems[ 0 ] == "usePipelineBuilderScript" )
      {
         // if load only then we don't use the pipeline script
         if ( engine.testLoadOnly )
         {
            console.noteln( "Use pipeline builder script [disabled by load only]" );
            cout( "\nUse pipeline builder script [disabled by load only]" );
         }
         else
         {
            console.noteln( "Use pipeline builder script: ", pItems[ 1 ] );
            cout( "\nUse pipeline builder script: " + pItems[ 1 ] );
            engine.usePipelineBuilderScript = pItems[ 1 ].toLowerCase() == "true";
         }
      }
      else if ( pItems.length == 2 && pItems[ 0 ] == "pipelineScriptFile" )
      {
         console.noteln( "Pipeline script file: ", pItems[ 1 ] );
         cout( "\nPipeline script file: " + pItems[ 1 ] );
         engine.pipelineScriptFile = pItems[ 1 ];
      }
      else if ( pItems.length == 1 && pItems[ 0 ] == "loadOnly" )
      {
         console.noteln( "Test load only" );
         cout( "\nTest load only" );
         engine.testLoadOnly = true;
         engine.recordTest = false;
         doPerform = false;
         // remove the test results if the test is simply loaded, the pipeline script is also ignored in loadOnly mode
         engine.executionStatus = undefined;
         engine.usePipelineScript = false;
         engine.usePipelineBuilderScript = false;
      }
      else if ( pItems.length == 1 && pItems[ 0 ] == "recordTest" && !engine.testLoadOnly )
      {
         console.noteln( "Record test" );
         cout( "\nRecord test" );
         doPerform = true;
         engine.recordTest = true;
         // remove the test results if the test is recorded
         engine.executionStatus = undefined;
      }
   }

   return doPerform;
}

/**
 * Parses command line parameters (non-test mode).
 * Handles keywords, dotted parameters, indexed parameters, and regular parameters.
 *
 * @param {object} engine - The WBPP engine instance
 * @returns {object} result - Object with { doPerform: boolean, dottedParams: object }
 */
function parseCommandLineParameters( engine )
{
   let doPerform = true;
   let dottedParams = {};

   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let pItems = Runtime.jsArguments[ i ].split( "=" );

      if ( pItems.length == 2 && pItems[ 0 ] != "file" && pItems[ 0 ] != "dir" )
      {
         console.noteln( "automation mode parameter: ", pItems[ 0 ], " = ", pItems[ 1 ] );

         if ( pItems[ 0 ] == "keywords" )
         {
            parseKeywordsParam( pItems[ 1 ], engine );
         }
         else if ( pItems[ 0 ].indexOf( "." ) >= 0 )
         {
            // Parameters with dots in their names (e.g., frameSelection.FWHM.enabled)
            // cannot be set via Parameters.set() - store them separately
            dottedParams[ pItems[ 0 ] ] = pItems[ 1 ];
         }
         else
         {
            // Check if this is an indexed parameter
            if ( !parseIndexedParam( pItems[ 0 ], pItems[ 1 ] ) )
            {
               // Regular parameter
               Parameters.set( pItems[ 0 ], pItems[ 1 ] );
            }
         }
      }
      else if ( pItems.length == 1 && pItems[ 0 ] == "loadOnly" )
      {
         console.noteln( "Load only mode (no testFile)" );
         cout( "\nLoad only mode" );
         engine.testLoadOnly = true;
         doPerform = false;
      }
   }

   return {
      doPerform: doPerform,
      dottedParams: dottedParams
   };
}

/**
 * Parses file and directory parameters from command line arguments.
 * Adds files to the engine.
 *
 * @param {object} engine - The WBPP engine instance
 */
function parseFileParameters( engine )
{
   let FITLIKE = [ "*.fit", "*.fits", "*.xisf", "*.FIT", "*.FITS", "*.XISF" ];
   function splitPF( v ) { let k = v.lastIndexOf( "|" ); return k < 0 ? { path: v, filter: "?" } : { path: v.substring(0,k), filter: v.substring(k+1) }; }
   for ( let i = 0; i < Runtime.jsArguments.length; ++i )
   {
      let pItems = Runtime.jsArguments[ i ].split( "=" );
      if ( pItems.length < 2 ) continue;
      let key = pItems[ 0 ], val = pItems.slice( 1 ).join( "=" );
      if ( key == "file" ) {
         let pf = splitPF( val );
         console.noteln( "add file: <raw>" + pf.path + "</raw> filter=" + pf.filter );
         engine.addFile( pf.path, ImageType.Unknown, pf.filter, 0, 0 );
      } else if ( key == "dir" ) {
         let pf = splitPF( val );
         console.noteln( "add directory: <raw>" + pf.path + "</raw> filter=" + pf.filter );
         let L = new FileList( pf.path, FITLIKE, false );
         L.files.forEach( filePath => engine.addFile( filePath, ImageType.Unknown, pf.filter, 0, 0 ) );
      }
   }
}

// ----------------------------------------------------------------------------
// Help documentation
// ----------------------------------------------------------------------------

/**
 * Prints the automation help documentation to the console.
 * Shows all available command line parameters for WBPP/FBPP automation.
 * The output is adapted based on the current mode (fastMode for FBPP).
 * Can be triggered by:
 *   - Running with paramList option: automationMode=true,paramList
 *   - Pressing Alt+A (Windows/Linux) or Option+A (macOS) in the GUI
 *
 * @param {boolean} fastMode - If true, shows FBPP-specific help (fewer options)
 */
function printAutomationHelp( fastMode )
{
   let separator = "======================================================================";
   let subSeparator = "----------------------------------------------------------------------";
   let col = 52; // column width for parameter names
   let scriptName = fastMode ? "FBPP" : "WBPP";
   let scriptFile = fastMode ? "FBPP.js" : "WBPP.js";

   // Helper function to pad parameter name to fixed width
   function p( param, desc )
   {
      if ( param.length >= col )
         console.noteln( param + "\n" + " ".repeat( col ) + desc );
      else
         console.noteln( param + " ".repeat( col - param.length ) + desc );
   }

   console.show();
   console.noteln( separator );
   console.noteln( scriptName + " Command Line Automation Help" );
   console.noteln( separator );
   console.noteln( "" );
   console.noteln( "USAGE:" );
   console.noteln( "" );
   console.noteln( "  Linux:" );
   console.noteln( "    /opt/PixInsight/bin/PixInsight.sh -n --automation-mode \\" );
   console.noteln( "      -r=\"[script],param=value,...\" --force-exit" );
   console.noteln( "" );
   console.noteln( "  macOS:" );
   console.noteln( "    /Applications/PixInsight/PixInsight.app/Contents/MacOS/PixInsight -n --automation-mode \\" );
   console.noteln( "      -r=\"[script],param=value,...\" --force-exit" );
   console.noteln( "" );
   console.noteln( "  Windows (cmd):" );
   console.noteln( "    \"C:\\Program Files\\PixInsight\\bin\\PixInsight.exe\" -n --automation-mode ^" );
   console.noteln( "      -r=\"[script],param=value,...\" --force-exit" );
   console.noteln( "" );
   console.noteln( "  Windows (PowerShell):" );
   console.noteln( "    & \"C:\\Program Files\\PixInsight\\bin\\PixInsight.exe\" -n --automation-mode `" );
   console.noteln( "      -r=\"[script],param=value,...\" --force-exit" );
   console.noteln( "" );
   console.noteln( "  [script] = path to " + scriptFile + " (e.g., /opt/PixInsight/src/scripts/...)" );
   console.noteln( "" );
   console.noteln( "SHORTCUT: Press Alt+A (Windows/Linux) or Option+A (macOS) to show this help." );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // SPECIAL PARAMETERS
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "SPECIAL PARAMETERS (custom syntax)" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "automationMode=true", "Enable automation mode (required for CLI)" );
   p( "dir=[path]", "Directory with input files, recursive scan (can repeat)" );
   p( "file=[path]", "Single input file (can repeat)" );
   p( "loadOnly", "Load configuration and open dialog without executing" );
   console.noteln( "" );
   console.noteln( "keywords=KEYWORD1;KEYWORD2 mode;KEYWORD3 mode" );
   console.noteln( "   Grouping keywords with optional mode: pre (default), post, prepost" );
   console.noteln( "   Example: keywords=SESSION;PANEL post;FILTER prepost" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // GENERAL OPTIONS
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "GENERAL OPTIONS" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "outputDirectory=[path]", "Output directory for processed files" );
   p( "smartNamingOverride=true|false", "Enable/disable smart naming override" );
   p( "detectMasterIncludingFullPath=true|false", "Use full path for master detection" );
   p( "fitsCoordinateConvention=0|1|2", "FITS orientation: 0=GlobalPref, 1=top-down, 2=bottom-up" );
   if ( !fastMode )
   {
      p( "generateRejectionMaps=true|false", "Generate rejection maps" );
      p( "preserveWhiteBalance=true|false", "Preserve white balance" );
   }
   p( "groupingKeywordsEnabled=true|false", "Enable keyword-based grouping" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // CALIBRATION
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "CALIBRATION" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "darkOptimizationLow=[float]", "Dark optimization low threshold (sigma)" );
   p( "darkExposureTolerance=[float]", "Dark exposure tolerance (seconds)" );
   p( "lightExposureTolerance=[float]", "Light exposure tolerance (seconds)" );
   p( "lightExposureTolerancePost=[float]", "Post-calibration exposure tolerance" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // OVERSCAN
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "OVERSCAN" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "overscanEnabled=true|false", "Enable overscan correction" );
   p( "overscanRegionEnabled_N=true|false", "Enable overscan region N (N=1..4)" );
   p( "overscanSourceX0_N=[int]", "Source region X0 for region N" );
   p( "overscanSourceY0_N=[int]", "Source region Y0 for region N" );
   p( "overscanSourceX1_N=[int]", "Source region X1 for region N" );
   p( "overscanSourceY1_N=[int]", "Source region Y1 for region N" );
   p( "overscanTargetX0_N=[int]", "Target region X0 for region N" );
   p( "overscanTargetY0_N=[int]", "Target region Y0 for region N" );
   p( "overscanTargetX1_N=[int]", "Target region X1 for region N" );
   p( "overscanTargetY1_N=[int]", "Target region Y1 for region N" );
   p( "overscanImageX0=[int]", "Image area X0" );
   p( "overscanImageY0=[int]", "Image area Y0" );
   p( "overscanImageX1=[int]", "Image area X1" );
   p( "overscanImageY1=[int]", "Image area Y1" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // IMAGE INTEGRATION
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "IMAGE INTEGRATION" );
   console.noteln( subSeparator );
   console.noteln( "" );
   console.noteln( "N = image type index: 1=Bias, 2=Dark, 3=Flat, 4=Light" );
   console.noteln( "" );
   console.noteln( "combination_N   0=Average, 1=Median, 2=Minimum, 3=Maximum" );
   console.noteln( "rejection_N     0=PercentileClip, 1=WinsorizedSigma, 2=LinearFit" );
   console.noteln( "                3=ESD, 4=RCR, 5=Auto" );
   console.noteln( "" );
   console.noteln( "Rejection algorithm parameters (indexed by N):" );
   p( "percentileLow_N=[float]", "Percentile clipping low" );
   p( "percentileHigh_N=[float]", "Percentile clipping high" );
   p( "sigmaLow_N=[float]", "Sigma low (Winsorized)" );
   p( "sigmaHigh_N=[float]", "Sigma high (Winsorized)" );
   p( "linearFitLow_N=[float]", "Linear fit clipping low" );
   p( "linearFitHigh_N=[float]", "Linear fit clipping high" );
   p( "ESD_Outliers_N=[float]", "ESD outliers fraction" );
   p( "ESD_Significance_N=[float]", "ESD significance" );
   p( "RCR_Limit_N=[float]", "RCR limit" );
   console.noteln( "" );
   p( "minWeight=[float]", "Minimum weight for integration (lights)" );
   console.noteln( "" );
   console.noteln( "Large scale rejection (flats):" );
   p( "flatsLargeScaleRejection=true|false", "Enable" );
   p( "flatsLargeScaleRejectionLayers=[int]", "Layers" );
   p( "flatsLargeScaleRejectionGrowth=[int]", "Growth" );
   console.noteln( "" );
   console.noteln( "Large scale rejection (lights):" );
   p( "lightsLargeScaleRejectionHigh=true|false", "Enable high rejection" );
   p( "lightsLargeScaleRejectionLayersHigh=[int]", "Layers (high)" );
   p( "lightsLargeScaleRejectionGrowthHigh=[int]", "Growth (high)" );
   p( "lightsLargeScaleRejectionLow=true|false", "Enable low rejection" );
   p( "lightsLargeScaleRejectionLayersLow=[int]", "Layers (low)" );
   p( "lightsLargeScaleRejectionGrowthLow=[int]", "Growth (low)" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // LINEAR PATTERN SUBTRACTION
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "LINEAR PATTERN SUBTRACTION" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "linearPatternSubtraction=true|false", "Enable LPS" );
   p( "linearPatternSubtractionRejectionLimit=[int]", "Rejection limit (sigma)" );
   p( "linearPatternSubtractionMode=[int]", "Mode" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // PLATE SOLVING
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "PLATE SOLVING" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "platesolve=true|false", "Enable plate solving" );
   if ( !fastMode )
      p( "platesolveFallbackManual=true|false", "Fall back to manual entry" );
   p( "imageSolverRa=[double]", "Right Ascension (degrees)" );
   p( "imageSolverDec=[double]", "Declination (degrees)" );
   p( "imageSolverObservationTime=[double]", "Observation time (Julian date)" );
   p( "imageSolverFocalLength=[float]", "Focal length (mm)" );
   p( "imageSolverPixelSize=[float]", "Pixel size (microns)" );
   p( "imageSolverForceDefaults=true|false", "Ignore image metadata, use defaults" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // IMAGE REGISTRATION and STAR DETECTION
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "IMAGE REGISTRATION and STAR DETECTION" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "imageRegistration=true|false", "Enable image registration" );
   console.noteln( "" );
   console.noteln( "pixelInterpolation=[0-10]: 0=NearestNeighbor, 1=Bilinear, 2=BicubicSpline," );
   console.noteln( "   3=BicubicBSpline, 4=Lanczos3, 5=Lanczos4, 6=Lanczos5," );
   console.noteln( "   7=MitchellNetravali, 8=CatmullRom, 9=CubicBSpline, 10=Auto" );
   console.noteln( "" );
   p( "clampingThreshold=[float]", "Clamping threshold" );
   p( "maxStars=[int]", "Maximum stars for registration" );
   p( "distortionCorrection=true|false", "Enable distortion correction" );
   p( "maxSplinePoints=[int]", "Maximum spline points" );
   p( "rigidTransformations=true|false", "Use rigid transformations only" );
   console.noteln( "" );
   p( "structureLayers=[int]", "Structure layers for star detection" );
   p( "hotPixelFilterRadius=[int]", "Hot pixel filter radius" );
   p( "noiseReductionFilterRadius=[int]", "Noise reduction filter radius" );
   p( "minStructureSize=[int]", "Minimum structure size (pixels)" );
   p( "sensitivity=[float]", "Detection sensitivity" );
   p( "peakResponse=[float]", "Peak response" );
   p( "brightThreshold=[float]", "Bright rejection threshold" );
   p( "maxStarDistortion=[float]", "Maximum star distortion" );
   p( "allowClusteredSources=true|false", "Allow clustered sources" );
   p( "useTriangleSimilarity=true|false", "Use triangle similarity" );
   console.noteln( "" );
   p( "referenceImage=[path]", "Reference image path (for method=0)" );
   console.noteln( "" );
   console.noteln( "bestFrameReferenceMethod=[0-2]: 0=Manual, 1=AutoSingle, 2=AutoByKeyword" );
   console.noteln( "bestFrameReferenceKeyword=[str]: FITS keyword for grouping (method=2 only)" );
   console.noteln( "   Example: bestFrameReferenceMethod=2,bestFrameReferenceKeyword=FILTER" );
   console.noteln( "            selects best reference per filter value" );
   console.noteln( "" );
   p( "reuseLastReferenceFrames=true|false", "Reuse last reference frames" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // SUBFRAME WEIGHTING (WBPP only)
   // -----------------------------------------------------------------------
   if ( !fastMode )
   {
      console.noteln( subSeparator );
      console.noteln( "SUBFRAME WEIGHTING" );
      console.noteln( subSeparator );
      console.noteln( "" );
      p( "subframeWeightingEnabled=true|false", "Enable subframe weighting" );
      p( "subframeWeightingPreset=[int]", "Weighting preset" );
      p( "subframesWeightsMethod=[int]", "Weights calculation method" );
      p( "FWHMWeight=[int]", "FWHM weight (0-100)" );
      p( "eccentricityWeight=[int]", "Eccentricity weight (0-100)" );
      p( "SNRWeight=[int]", "SNR weight (0-100)" );
      p( "starsWeight=[int]", "Stars count weight (0-100)" );
      p( "PSFSignalWeight=[int]", "PSF Signal weight (0-100)" );
      p( "PSFSNRWeight=[int]", "PSF SNR weight (0-100)" );
      p( "pedestal=[int]", "Pedestal value" );
      console.noteln( "" );
   }

   // -----------------------------------------------------------------------
   // FRAME SELECTION
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "FRAME SELECTION" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "frameSelectionEnabled=true|false", "Enable frame selection" );
   p( "frameSelectionInteractive=true|false", "Interactive mode (set false for CLI)" );
   console.noteln( "" );
   console.noteln( "Filter parameters pattern: frameSelection.[metric].[property]" );
   console.noteln( "Available metrics: FWHM, eccentricity, SNR, PSFSignalWeight, median, numberOfStars, custom" );
   console.noteln( "Note: PSFSignalWeight is normalized per group (0-1 range, best frame = 1)" );
   console.noteln( "" );
   p( "frameSelection.[metric].enabled=true|false", "Enable filter" );
   p( "frameSelection.[metric].value=[number]", "Threshold value" );
   p( "frameSelection.[metric].compareMode=0|1", "0=LESS_THAN, 1=GREATER_THAN" );
   p( "frameSelection.custom.formula=[expr]", "Custom formula (e.g., SNR/FWHM)" );
   console.noteln( "" );
   console.noteln( "Example: Accept frames with FWHM less than 3.5 and PSFSignalWeight greater than 0.2:" );
   console.noteln( "   frameSelection.FWHM.enabled=true,frameSelection.FWHM.value=3.5," );
   console.noteln( "   frameSelection.FWHM.compareMode=0,frameSelection.PSFSignalWeight.enabled=true," );
   console.noteln( "   frameSelection.PSFSignalWeight.value=0.2,frameSelection.PSFSignalWeight.compareMode=1" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // LOCAL NORMALIZATION (WBPP only)
   // -----------------------------------------------------------------------
   if ( !fastMode )
   {
      console.noteln( subSeparator );
      console.noteln( "LOCAL NORMALIZATION" );
      console.noteln( subSeparator );
      console.noteln( "" );
      p( "localNormalization=true|false", "Enable local normalization" );
      p( "localNormalizationInteractiveMode=true|false", "Interactive mode" );
      p( "localNormalizationGenerateImages=true|false", "Generate LN images" );
      console.noteln( "" );
      console.noteln( "localNormalizationMethod=[0-1]: 0=PSFFlux, 1=MultiscaleAnalysis" );
      console.noteln( "localNormalizationBestReferenceSelectionMethod=[0-4]:" );
      console.noteln( "   0=PSFSW, 1=PSFSNR, 2=MSTAR, 3=MEDIAN, 4=STARS" );
      console.noteln( "localNormalizationReferenceFrameGenerationMethod=[0-1]:" );
      console.noteln( "   0=SingleBest, 1=IntegrationBestFrames" );
      console.noteln( "localNormalizationPsfType=[0-6]:" );
      console.noteln( "   0=Gaussian, 1=Moffat1.5, 2=Moffat4, 3=Moffat6, 4=Moffat8, 5=Moffat10, 6=Auto" );
      console.noteln( "" );
      p( "localNormalizationMaxIntegratedFrames=[int]", "Max frames per integration" );
      p( "localNormalizationGridSize=[int]", "Grid size" );
      p( "localNormalizationPsfGrowth=[float]", "PSF growth" );
      p( "localNormalizationPsfMaxStars=[int]", "Max stars for PSF" );
      p( "localNormalizationPsfMinSNR=[float]", "Min SNR for PSF" );
      p( "localNormalizationPsfAllowClusteredSources=true|false", "Allow clustered sources" );
      p( "localNormalizationLowClippingLevel=[float]", "Low clipping level" );
      p( "localNormalizationHighClippingLevel=[float]", "High clipping level" );
      p( "reuseLastLNReferenceFrames=true|false", "Reuse LN reference frames" );
      console.noteln( "" );
   }

   // -----------------------------------------------------------------------
   // OUTPUT and POST-PROCESSING
   // -----------------------------------------------------------------------
   console.noteln( subSeparator );
   console.noteln( "OUTPUT and POST-PROCESSING" );
   console.noteln( subSeparator );
   console.noteln( "" );
   p( "integrate=true|false", "Run image integration" );
   p( "autocrop=true|false", "Auto-crop integrated images" );
   console.noteln( "" );
   console.noteln( "debayerOutputMethod=[0-2]: 0=CombinedRGB, 1=SeparateChannels, 2=Both" );
   console.noteln( "" );
   p( "recombineRGB=true|false", "Recombine RGB channels" );
   p( "debayerActiveChannelR=true|false", "Process Red channel" );
   p( "debayerActiveChannelG=true|false", "Process Green channel" );
   p( "debayerActiveChannelB=true|false", "Process Blue channel" );
   console.noteln( "" );

   // -----------------------------------------------------------------------
   // PIPELINE SCRIPTING (WBPP only)
   // -----------------------------------------------------------------------
   if ( !fastMode )
   {
      console.noteln( subSeparator );
      console.noteln( "PIPELINE SCRIPTING" );
      console.noteln( subSeparator );
      console.noteln( "" );
      p( "usePipelineScript=true|false", "Enable pipeline script" );
      p( "pipelineScriptFile=[path]", "Pipeline script file path" );
      p( "usePipelineBuilderScript=true|false", "Enable pipeline builder" );
      p( "pipelineBuilderScriptFile=[path]", "Pipeline builder file path" );
      console.noteln( "" );
   }

   console.noteln( separator );
}

// ----------------------------------------------------------------------------
// EOF BPP-Automation.js - Released 2026-05-10T11:05:00Z
