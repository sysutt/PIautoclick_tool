// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Solver.js - Released 2026-05-10T11:05:00Z
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

#define USE_SOLVER_LIBRARY true
#define SETTINGS_MODULE "SOLVER"
#define STAR_CSV_FILE   File.systemTempDirectory + "/stars.csv"
#include "BPP_ImageSolverStub.js"

/**
 * PlateSolver domain class -- handles astrometric plate solving.
 *
 * Wraps the ImageSolver to provide plate-solving capabilities
 * for the BatchPreprocessing pipeline.
 */
var PlateSolver = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   /**
    * Resets all ImageSolver configuration parameters to defaults.
    *
    * @param {ImageSolver} solver - The ImageSolver instance to configure.
    */
   resetConfiguration( solver )
   {
      /*
       * Default parameters for ImageSolver version 6.3.1 (core version 1.9.2)
       */
      solver.solverCfg.useActive = true;
      solver.solverCfg.files = [];
      solver.solverCfg.catalogMode = CatalogMode.Automatic;
      solver.solverCfg.vizierServer = "https://vizier.cds.unistra.fr/";
      solver.solverCfg.magnitude = 12;
      solver.solverCfg.maxIterations = 100;
      solver.solverCfg.structureLayers = 5;
      solver.solverCfg.minStructureSize = 0;
      solver.solverCfg.hotPixelFilterRadius = 1;
      solver.solverCfg.noiseReductionFilterRadius = 0;
      solver.solverCfg.sensitivity = 0.5;
      solver.solverCfg.peakResponse = 0.5;
      solver.solverCfg.brightThreshold = 3.0;
      solver.solverCfg.maxStarDistortion = 0.6;
      solver.solverCfg.autoPSF = false;
      solver.solverCfg.generateErrorImg = false;
      solver.solverCfg.showStars = false;
      solver.solverCfg.catalog = "PPMXL";
      solver.solverCfg.autoMagnitude = true;
      solver.solverCfg.showStarMatches = false;
      solver.solverCfg.showSimplifiedSurfaces = false;
      solver.solverCfg.showDistortion = false;
      solver.solverCfg.distortionCorrection = true;
      solver.solverCfg.rbfType = WCS_DEFAULT_RBF_TYPE;
      solver.solverCfg.maxSplinePoints = WCS_DEFAULT_MAX_SPLINE_POINTS;
      solver.solverCfg.splineOrder = 2;
      solver.solverCfg.splineSmoothing = 0.005;
      solver.solverCfg.enableSimplifier = true;
      solver.solverCfg.simplifierRejectFraction = 0.10;
      solver.solverCfg.outlierDetectionRadius = 160;
      solver.solverCfg.outlierDetectionMinThreshold = 4.0;
      solver.solverCfg.outlierDetectionSigma = 5.0;
      solver.solverCfg.generateDistortModel = false;
      solver.solverCfg.outSuffix = "_ast";
      solver.solverCfg.projection = 0;
      solver.solverCfg.projectionOriginMode = 0;
      solver.solverCfg.restrictToHQStars = false;
      solver.solverCfg.intersectionMode = IntersectionMode.Automatic;
      solver.solverCfg.tryApparentCoordinates = true;
      solver.solverCfg.tryExhaustiveInitialAlignment = false;
   }

   /**
    * Initializes solver metadata from engine properties.
    *
    * @param {ImageSolver} solver - The ImageSolver instance.
    * @param {ImageWindow} imageWindow - The image window to initialize from.
    * @returns {Boolean} true if initialization succeeded, false otherwise.
    */
   initializeSolver( solver, imageWindow )
   {
      let engine = this.engine;

      function defaults()
      {
         solver.metadata.dec = engine.imageSolverDec;
         solver.metadata.startTime =
            solver.metadata.observationTime = engine.imageSolverObservationTime;
         solver.metadata.focal = engine.imageSolverFocalLength;
         solver.metadata.ra = engine.imageSolverRa;
         solver.metadata.referenceSystem = "ICRS";
         solver.metadata.topocentric = false;
         solver.metadata.useFocal = true;
         solver.metadata.xpixsz = engine.imageSolverPixelSize;
         // derived
         solver.metadata.resolution = isNaN( solver.metadata.focal ) ? 0 : solver.metadata.xpixsz / solver.metadata.focal * 0.18 / Math.PI;
         solver.metadata.SaveParameters();
      }

      try
      {
         // always init the default values
         defaults();
         solver.initialize( imageWindow, engine.imageSolverForceDefaults );

         // Ensure observationTime is valid after initialize().
         // When forceDefaults is false, ExtractMetadata runs last and can
         // set observationTime (and startTime) to null if the master image
         // has no DATE-OBS/Observation:Time:Start properties.
         if ( !solver.metadata.observationTime )
         {
            if ( imageWindow && imageWindow.isWindow )
            {
               let wcs = new WCSKeywords();
               wcs.Read( imageWindow );
               if ( wcs.observationTime )
                  solver.metadata.observationTime = wcs.observationTime;
            }
            if ( !solver.metadata.observationTime )
               solver.metadata.observationTime = engine.imageSolverObservationTime;
         }


         return true;
      }
      catch ( e )
      {
         console.warningln( e );
         return false;
      }
   }

   /**
    * Executes plate solving and saves results to engine on success.
    *
    * @param {ImageSolver} solver - The ImageSolver instance.
    * @param {ImageWindow} image - The image window to solve.
    * @returns {Boolean} true if solving succeeded, false otherwise.
    */
   executeSolver( solver, image )
   {
      try
      {
         // solveImage() returns void; throws on failure.
         solver.solveImage( image );

         // save configuration and metadata on success
         solver.solverCfg.SaveSettings();
         solver.solverCfg.SaveParameters();
         solver.metadata.SaveSettings();
         solver.metadata.SaveParameters();

         this.engine.imageSolverObservationTime = solver.metadata.observationTime;
         this.engine.imageSolverDec = solver.metadata.dec;
         this.engine.imageSolverRa = solver.metadata.ra;
         this.engine.imageSolverFocalLength = solver.metadata.focal;
         this.engine.imageSolverPixelSize = solver.metadata.xpixsz;

         return true;
      }
      catch ( e )
      {
         solver.error = e.toString();
         console.warningln( e );
         return false;
      }
   }

   /**
    * Plate-solves the given image window.
    *
    * @param {ImageWindow} referenceImageWindow - The image to be solved.
    * @param {Object} [solverCfgOverrides] - Optional key/value pairs to configure the solver.
    * @param {Object} [overrides] - Optional key/value metadata values to override.
    * @returns {undefined|ImageSolver} Returns undefined if plate solve failed, or the solver instance on success.
    */
   solveImage( referenceImageWindow, solverCfgOverrides, overrides )
   {
      let engine = this.engine;
      let solver = new ImageSolver();
      if ( this.initializeSolver( solver, referenceImageWindow ) )
      {
         this.resetConfiguration( solver );
         if ( overrides != undefined )
         {
            let keys = Object.keys( overrides );
            keys.forEach( k =>
            {
               solver.metadata[ k ] = overrides[ k ];
            } );
         }
         let stfApplied = false;
         if ( solverCfgOverrides )
         {
            let keys = Object.keys( solverCfgOverrides );
            for ( let i = 0; i < keys.length; ++i )
               solver.solverCfg[ keys[ i ] ] = solverCfgOverrides[ keys[ i ] ];
         }

         for ( ;; )
         {
            if ( solver.error )
               console.warningln( solver.error );

            if ( solver.solverCfg.distortionCorrection == false )
            {
               // warning: distortion correction must be enabled
               ( new MessageBox( "<p>Distortion correction must be enabled to compute an accurate astrometric solution.</p>",
                  "Plate Solving",
                  StdIcon.Warning,
                  StdButton.Ok ) ).execute();
            }
            else
            {
               if ( this.executeSolver( solver, referenceImageWindow ) )
                  // solved
                  break;
               else if ( !engine.platesolveFallbackManual )
                  // if manual fallback is not checked then we do not attempt to present the interactive GUI
                  return undefined;
            }

            // solver failed, prepare the interactive mode
            engine.operationQueue.hideExecutionMonitorDialog();
            if ( !stfApplied )
            {
               referenceImageWindow.mainView.stf = WBPPUtils.computeSTFAutoStretch( referenceImageWindow.mainView );
               referenceImageWindow.fitWindow();
               referenceImageWindow.position = new Point( 0, 0 );
               stfApplied = true;
            }

            referenceImageWindow.show();
            console.hide();
            let dialog = new ImageSolverDialog( solver.solverCfg, solver.metadata, false /*showTargetImage*/ );
            let res = dialog.execute();
            referenceImageWindow.hide();
            console.show();
            if ( res == 0 )
               return undefined;

            solver.solverCfg = dialog.solverCfg;
            solver.metadata = dialog.metadata;
         }

         return solver;
      }
      return undefined;
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-Solver.js - Released 2026-05-10T11:05:00Z
