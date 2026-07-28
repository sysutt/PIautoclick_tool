// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Pipeline.js - Released 2026-05-10T11:05:00Z
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

var PipelineManager = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   // ........................................................................

   /**
    * Initialize the processing.
    * To be invoked before starting the pipeline.
    */
   initializeExecution()
   {
      let engine = this.engine;
      engine.groupsManager.initializeProcessing();
      // V8: ProcessContainer.add() is not available; use a no-op shim.
      // The shim must NOT accumulate native process references to avoid
      // exhausting the V8 sandbox heap during long pipelines.
      try
      {
         let pc = new ProcessContainer();
         if ( typeof pc.add === 'function' )
            engine.processContainer = pc;
         else
            throw 0;
      }
      catch ( e )
      {
         engine.processContainer = {
            add: function( process ) {},
            toSource: function() { return ""; }
         };
      }
      engine.executionTimestamp = WBPPUtils.timestampString();
      engine.logsFileName = WBPPUtils.existingDirectory( engine.outputDirectory + "/logs" ) + "/" + engine.executionTimestamp + ".log";
      engine.consoleLogger.initialize( engine.title, engine.version, engine.logsFileName );
   }

   // ........................................................................

   flushProcessContainer()
   {
      let engine = this.engine;
      // store the log timestamp
      let prefix = engine.fastMode ? "F" : "W";
      let filePath = WBPPUtils.existingDirectory( engine.outputDirectory + "/logs" ) + "/" + engine.executionTimestamp + "_ProcessContainer.xpsm";
      let str = "<?xml version=\"1.0\" ";
      str += "encoding=\"UTF-8\"?>\n<xpsm version=\"1.0\"";
      str += " xmlns=\"http://www.pixinsight.com/xpsm\"";
      str += " xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"";
      str += " xsi:schemaLocation=\"http://www.pixinsight.com/xpsm";
      str += " http://pixinsight.com/xpsm/xpsm-1.0.xsd\">\n";
      str += engine.processContainer.toSource( "XPSM 1.0", "BPP_ProcessContainer" /*varId*/ ,
         0 /*indentSize*/ ,
         SourceCodeFlag.NoTimeInfo | SourceCodeFlag.NoReadOnlyParams | SourceCodeFlag.NoDescription ).trim() + "\n";
      str += "<icon id=\"" + prefix + "BPP_ProcessContainer_" + engine.executionTimestamp + "\" instance=\"ProcessContainer_instance\" xpos=\"100\" ypos=\"100\" workspace=\"BPP\"/>\n</xpsm>";

      File.writeTextFile( filePath, str );
   }

   // ........................................................................

   /**
    * Performs the post-execution actions.
    *
    */
   postExecutionActions()
   {
      let engine = this.engine;
      console.writeln();
      console.writeln( "Smart report result" );
      console.writeln();
      console.writeln( engine.processLogger.toString() );
      console.resetStatus();
   }

   // ........................................................................

   resetRequiredSpace()
   {
      let engine = this.engine;
      // Space required
      engine.WS = {
         masterBias:
         {
            label: "Master bias",
            size: 0
         },
         masterDark:
         {
            label: "Master darks",
            size: 0
         },
         masterFlat:
         {
            label: "Master flats",
            size: 0
         },
         calibrationFlat:
         {
            label: "Calibrated flats",
            size: 0
         },
         calibrationLight:
         {
            label: "Calibrated lights",
            size: 0
         },
         LPS:
         {
            label: "Linear pattern subtraction",
            size: 0
         },
         cosmeticCorrection:
         {
            label: "Cosmetic correction",
            size: 0
         },
         debayer:
         {
            label: "Debayer",
            size: 0
         },
         imageWeighting:
         {
            label: "Image Weighting",
            size: 0,
         },
         registration:
         {
            label: "Registration",
            size: 0
         },
         localNormalization:
         {
            label: "Local normalization",
            size: 0
         },
         integration:
         {
            label: "Master lights",
            size: 0
         },
         fastIntegration:
         {
            label: "Fast integration",
            size: 0
         },
         recombination:
         {
            label: "Channel recombination",
            size: 0
         }
      }
   }

   // ........................................................................

   buildExecutionPipeline()
   {
      let engine = this.engine;
      engine.operationQueue.clear();
      this.resetRequiredSpace();
      this.buildPipelineForBias();
      this.buildPipelineForDark();
      this.buildPipelineForFlat();
      // we bild the defaul pipeline for lights if no pipeline builder is defined
      // or if its execution fails
      engine.pipelineBuilderError = "";
      if ( !this.runPipelineBuilder() )
         this.buildPipelineForLight();
   }

   // ........................................................................

   runPipeline()
   {
      let engine = this.engine;
      engine.parametersManager.saveRunningConfiguration();

      if ( engine.usePipelineScript )
         engine.operationQueue.installEventScript( engine.pipelineScriptFile );
      else
         engine.operationQueue.uninstallEventScript();

      engine.operationQueue.run();
   }

   // ........................................................................

   runPipelineBuilder()
   {
      let engine = this.engine;
      if ( !engine.usePipelineBuilderScript )
         return false;

      if ( engine.pipelineBuilderScriptFile == "" )
         return false;

      if ( !File.exists( engine.pipelineBuilderScriptFile ) )
      {
         engine.pipelineBuilderError = "Script file not found";
         return false;
      }

      let scriptCode = File.readTextFile( engine.pipelineBuilderScriptFile );
      if ( scriptCode == "" )
      {
         engine.pipelineBuilderError = "The script file is empty";
         return false;
      }

      let code = "let success = false; { " + scriptCode + " }; success = true; success";
      let success = false;
      try
      {
         success = eval( code );
      }
      catch ( e )
      {
         success = false;
         engine.pipelineBuilderError = "Script execution failed.";
         console.warningln( "** Warning: Pipeline builder script failed." );
         console.warningln( e.name );
         console.warningln( e.message );
         console.warningln( e.stack );
      }
      return success;
   }

   // ........................................................................

   /**
    * Generates the pipeline steps to process the bias frames.
    */
   buildPipelineForBias()
   {
      let engine = this.engine;
      // process only pre-process groups
      let groupsPRE = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      for ( let i = 0; i < groupsPRE.length; ++i )
         if ( groupsPRE[ i ].imageType == ImageType.Bias && !groupsPRE[ i ].hasMaster )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPRE[ i ]
            };

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringHeader( 'MASTER BIAS GENERATION' ) );
            }, logEnv )
            // integration step
            let integrationOperation = new engine.ImageIntegrationOperation( groupsPRE[ i ] );
            engine.WS.masterBias.size += integrationOperation.spaceRequired();
            engine.operationQueue.addOperation( integrationOperation );
            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringFooter() );
               env.params.processLogger.newLine();
            }, logEnv )
         }
   }

   // ........................................................................

   /**
    * Generates the pipeline steps to process the dark frames.
    */
   buildPipelineForDark()
   {
      let engine = this.engine;
      // process only pre-process groups
      let groupsPRE = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      for ( let i = 0; i < groupsPRE.length; ++i )
         if ( groupsPRE[ i ].imageType == ImageType.Dark && !groupsPRE[ i ].hasMaster )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPRE[ i ]
            };

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringHeader( 'MASTER DARK GENERATION' ) );
            }, logEnv );
            // integration step
            let integrationOperation = new engine.ImageIntegrationOperation( groupsPRE[ i ] );
            engine.WS.masterDark.size += integrationOperation.spaceRequired();
            engine.operationQueue.addOperation( integrationOperation );
            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringFooter() );
               env.params.processLogger.newLine();
            }, logEnv );
         }
   }

   // ........................................................................

   /**
    * Generates the pipeline steps to process the flat frames.
    */
   buildPipelineForFlat()
   {
      let engine = this.engine;

      // process only pre-process groups
      let groupsPRE = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      // flats calibration operations
      for ( let i = 0; i < groupsPRE.length; ++i )
         if ( groupsPRE[ i ].imageType == ImageType.Flat && !groupsPRE[ i ].hasMaster )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPRE[ i ]
            };

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringHeader( 'MASTER FLAT GENERATION' ) );
            }, logEnv );
            // calibration step (only if calibration masters are found)
            let cg = engine.calibrationMatcher.getCalibrationGroupsFor( groupsPRE[ i ] );
            if ( cg.masterBias || cg.masterDark || engine.overscan.enabled )
            {
               let calibrationOperation = new engine.calibrationOperation( groupsPRE[ i ] );
               engine.WS.calibrationFlat.size += calibrationOperation.spaceRequired();
               engine.operationQueue.addOperation( calibrationOperation );
            }
            // integration step
            let integrationOperation = new engine.ImageIntegrationOperation( groupsPRE[ i ] );
            engine.WS.masterFlat.size += integrationOperation.spaceRequired();
            engine.operationQueue.addOperation( integrationOperation );
            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringFooter() );
               env.params.processLogger.newLine();
            }, logEnv );
         }
   }

   // ........................................................................

   /**
    * Generates the pipeline steps to process the light frames.
    */
   buildPipelineForLight()
   {
      let engine = this.engine;
      // pre-process groups first
      let groupsPRE = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );

      // CALIBRATION
      for ( let i = 0; i < groupsPRE.length; ++i )
         if ( groupsPRE[ i ].imageType == ImageType.Light )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPRE[ i ]
            };

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.newLine();
               env.params.processLogger.addMessage( env.params.group.logStringHeader( 'LIGHT FRAMES CALIBRATION' ) );
            }, logEnv );

            // calibration step (only if calibration masters are found)
            let cg = engine.calibrationMatcher.getCalibrationGroupsFor( groupsPRE[ i ] );
            if ( cg.masterBias || cg.masterDark || cg.masterFlat )
            {
               let calibrationOperation = new engine.calibrationOperation( groupsPRE[ i ] );
               engine.WS.calibrationLight.size += calibrationOperation.spaceRequired();
               engine.operationQueue.addOperation( calibrationOperation );
            }

            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringFooter() );
               env.params.processLogger.newLine();
            }, logEnv );
         }

      // LINEAR PATTERN SUBTRACTION
      if ( engine.linearPatternSubtraction )
      {
         let logEnv = {
            processLogger: engine.processLogger
         };

         // log header
         engine.operationQueue.addOperationBlock( ( env ) =>
         {
            env.params.processLogger.newLine();
            env.params.processLogger.addMessage( "<b>********************</b> <i>LINEAR DEFECTS CORRECTION</i> <b>********************</b>" );
         }, logEnv );

         let LPSOperation = new engine.LPSOperation();
         engine.WS.LPS.size += LPSOperation.spaceRequired();
         engine.operationQueue.addOperation( LPSOperation );

         // log footer
         engine.operationQueue.addOperationBlock( ( env ) =>
         {
            env.params.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
            env.params.processLogger.newLine();
         }, logEnv );
      }

      // COSMETIC CORRECTON AND DEBAYER

      for ( let i = 0; i < groupsPRE.length; ++i )
         if ( groupsPRE[ i ].imageType == ImageType.Light )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPRE[ i ]
            };

            let needsCC = groupsPRE[ i ].ccData.CCTemplate && groupsPRE[ i ].ccData.CCTemplate.length > 0;
            let needsDebayer = groupsPRE[ i ].isCFA;

            if ( !needsCC && !needsDebayer )
               continue;

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.newLine();
               env.params.processLogger.addMessage( env.params.group.logStringHeader( ( needsCC ? "COSMETIZATION" : "" ) + ( needsCC && needsDebayer ? " and " : "" ) + ( needsDebayer ? "DEBAYERING" : "" ) ) );
            }, logEnv );

            // cosmetic correction
            if ( needsCC )
            {
               let cosmeticCorretcionOperation = new engine.CosmeticCorrectionOperation( groupsPRE[ i ] );
               engine.WS.cosmeticCorrection.size += cosmeticCorretcionOperation.spaceRequired();
               engine.operationQueue.addOperation( cosmeticCorretcionOperation );
            }

            // debayer
            if ( needsDebayer )
            {
               let debayerOperation = new engine.DebayerOperation( groupsPRE[ i ] );
               engine.WS.debayer.size += debayerOperation.spaceRequired();
               engine.operationQueue.addOperation( debayerOperation );
            }

            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( env.params.group.logStringFooter() );
               env.params.processLogger.newLine();
            }, logEnv );
         }

      // REFERENCE FRAME DATA PREPARATION
      if ( !engine.reuseLastReferenceFrames )
         engine.operationQueue.addOperation( new engine.ReferenceFrameDataPreparationOperation() );

      // POST-PROCESS GROUPS
      let groupsPOST = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).filter( g => g.isActive );

      // MEASUREMENT OPERATION
      let generateSubframesWeights = engine.subframeWeightingEnabled && ( ( engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.FORMULA ) || engine.integrate );
      let measureForBestFrameSelection = ( engine.imageRegistration || engine.fastMode ) && engine.bestFrameReferenceMethod != BPP.BestReferenceMethod.MANUAL && !engine.reuseLastReferenceFrames;
      // Measure frames if frames selection is enabled (for interactive selection)
      let measureForFrameSelection = engine.frameSelectionEnabled;
      let measureImages = generateSubframesWeights || measureForBestFrameSelection || engine.localNormalization || measureForFrameSelection;
      if ( !engine.groupsManager.isEmpty() && measureImages )
      {
         engine.operationQueue.addOperation( new engine.MeasurementOperation() );
         if ( engine.subframeWeightingEnabled && ( engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.FORMULA ) )
            engine.operationQueue.addOperation( new engine.CustomFormulaWeightsGenerationOperation() );
         // Interactive frames selection - runs after measurements and weights generation
         if ( engine.frameSelectionEnabled )
            engine.operationQueue.addOperation( new engine.FrameSelectionOperation() );
         if ( ( engine.subframesWeightsMethod != BPP.SubframeWeightsMethod.PSFScaleSNR ) && engine.integrate && engine.groupsManager.regularIntegrationGroupExists() )
            engine.operationQueue.addOperation( new engine.BadFramesRejectionOperation() );
      }

      // SET THE REFERENCE FRAME (for both post calibration group with or without fast integration )
      let regularRegistrationGropuExists = engine.imageRegistration && engine.groupsManager.regularIntegrationGroupExists();
      if ( !engine.groupsManager.isEmpty() && ( regularRegistrationGropuExists || ( engine.groupsManager.fastIntegrationGroupExists() && engine.integrate ) ) )
         if ( !engine.reuseLastReferenceFrames )
            engine.operationQueue.addOperation( new engine.ReferenceFrameSelectionOperation() );

      // exit if no registration, local normalization and integration needs to be performed
      if ( !generateSubframesWeights && !engine.imageRegistration && !engine.localNormalization && !engine.integrate )
         return;

      // POST-PROCESS GROUPS - REGISTRATION
      if ( engine.imageRegistration )
         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB && !groupsPOST[ i ].fastIntegrationData.enabled;

            if ( standardPostCalibrationProcessing )
            {
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'IMAGE REGISTRATION' ) );
               }, logEnv )

               let registrationOperation = new engine.RegistrationOperation( groupsPOST[ i ] );
               engine.WS.registration.size += registrationOperation.spaceRequired();
               engine.operationQueue.addOperation( registrationOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv )
            }
         }

      // POST-PROCESS GROUPS - LOCAL NORMALIZATION REFERENCE FRAME SELECTION
      if ( engine.localNormalization )
         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB && !groupsPOST[ i ].fastIntegrationData.enabled;

            if ( standardPostCalibrationProcessing )
            {
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'LOCAL NORMALIZATION - REFERENCE FRAME SELECTION' ) );
               }, logEnv );

               if ( !engine.reuseLastLNReferenceFrames )
               {
                  let lnReferenceFrameSelectionOperation = new engine.LocalNormalizationReferenceFrameSelectionOperation( groupsPOST[ i ] );
                  engine.WS.localNormalization.size += lnReferenceFrameSelectionOperation.spaceRequired();
                  engine.operationQueue.addOperation( lnReferenceFrameSelectionOperation );
               }

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

      // POST-PROCESS GROUPS - LOCAL NORMALIZATION
      if ( engine.localNormalization )
         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB && !groupsPOST[ i ].fastIntegrationData.enabled;

            if ( standardPostCalibrationProcessing )
            {
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'LOCAL NORMALIZATION' ) );
               }, logEnv );

               let lnOperation = new engine.LocalNormalizationOperation( groupsPOST[ i ] );
               engine.WS.localNormalization.size += lnOperation.spaceRequired();
               engine.operationQueue.addOperation( lnOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

      // POST-PROCESS GROUPS - IMAGE INTGEGRATION

      if ( engine.integrate )
      {
         // REGULAR INTEGRATION

         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB;

            if ( standardPostCalibrationProcessing && !groupsPOST[ i ].fastIntegrationData.enabled )
            {

               // Image Integration
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'IMAGE INTEGRATION' ) );
               }, logEnv );

               let imageIntegrationOperation = new engine.ImageIntegrationOperation( groupsPOST[ i ] );
               engine.WS.integration.size += imageIntegrationOperation.spaceRequired();
               engine.operationQueue.addOperation( imageIntegrationOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

         // FAST INTEGRATION

         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB;

            if ( standardPostCalibrationProcessing && groupsPOST[ i ].fastIntegrationData.enabled )
            {
               // Fast Integration
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'FAST INTEGRATION' ) );
               }, logEnv );


               let fastIntegrationOperation = new engine.FastIntegrationOperation( groupsPOST[ i ] );
               engine.WS.fastIntegration.size += fastIntegrationOperation.spaceRequired();
               let imageIntegrationOperation = new engine.ImageIntegrationOperation( groupsPOST[ i ] );
               engine.WS.integration.size += imageIntegrationOperation.spaceRequired();
               engine.operationQueue.addOperation( fastIntegrationOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

         // DRIZZLE INTEGRATION

         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let standardPostCalibrationProcessing = groupsPOST[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB;

            if ( standardPostCalibrationProcessing && groupsPOST[ i ].isDrizzleEnabled() )
            {
               // Drizzle Integration
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'DRIZZLE INTEGRATION' ) );
               }, logEnv );

               let drizzleIntegrationOperation = new engine.DrizzleIntegrationOperation( groupsPOST[ i ] );
               engine.WS.integration.size += drizzleIntegrationOperation.spaceRequired();
               engine.operationQueue.addOperation( drizzleIntegrationOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

         // AUTO CROP

         if ( engine.integrate && engine.autocrop && groupsPOST.length > 0 )
         {
            let logEnv = {
               processLogger: engine.processLogger
            };

            // log header
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               console.writeln();
               env.params.processLogger.addMessage( "<b>*********************** <i>AUTO CROP</i> ***********************</b>" );
               console.writeln( BPP.Format.SEPARATOR );
               console.writeln( "* Begin autocrop of master light frames." );
               console.writeln( BPP.Format.SEPARATOR );
            }, logEnv );

            let autocropOperation = new engine.AutoCropOperation();
            engine.WS.integration.size += autocropOperation.spaceRequired();
            engine.operationQueue.addOperation( autocropOperation );

            // log footer
            engine.operationQueue.addOperationBlock( ( env ) =>
            {
               env.params.processLogger.addMessage( "<b>" + BPP.Format.SEPARATOR + "</b>" );
               env.params.processLogger.newLine();
               console.writeln( BPP.Format.SEPARATOR );
               console.writeln( "* End autocrop of master light frames." );
               console.writeln( BPP.Format.SEPARATOR );
            }, logEnv );
         }

         // process the RGB recombination groups, this needs to be done at the end to ensure that all
         // gray R,G and B masters have been integrated
         for ( let i = 0; i < groupsPOST.length; ++i )
         {
            let logEnv = {
               processLogger: engine.processLogger,
               group: groupsPOST[ i ]
            };

            // RGB RECOMBINATION
            if ( groupsPOST[ i ].associatedRGBchannel == BPP.AssociatedChannel.COMBINED_RGB )
            {
               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'RGB COMBINATION' ) );
               }, logEnv );

               // RGB Recombination
               let recombinationOperation = new engine.RGBRecombinationOperation( groupsPOST[ i ] );
               engine.WS.recombination.size += recombinationOperation.spaceRequired();
               engine.operationQueue.addOperation( recombinationOperation );

               // log footer
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter() );
                  env.params.processLogger.newLine();
               }, logEnv );
            }
         }

         // Plate solve
         if ( engine.integrate && engine.platesolve )
         {

            for ( let i = 0; i < groupsPOST.length; ++i )
            {
               // Image Integration
               let logEnv = {
                  processLogger: engine.processLogger,
                  group: groupsPOST[ i ]
               };

               // log header
               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringHeader( 'ASTROMETRIC SOLUTION' ) );
               }, logEnv );

               let plateSolveOperation = new engine.PlateSolveOperation( groupsPOST[ i ] );
               engine.operationQueue.addOperation( plateSolveOperation );

               engine.operationQueue.addOperationBlock( ( env ) =>
               {
                  env.params.processLogger.addMessage( env.params.group.logStringFooter( 'COMPLETED' ) );
               }, logEnv );
            }
         }
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-Pipeline.js - Released 2026-05-10T11:05:00Z
