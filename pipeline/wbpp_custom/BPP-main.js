// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Main.js - Released 2026-05-10T11:05:00Z
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

#include "BPP-Global.js"     // global defines
#include "BPP-Helper.js"     // helper functions
#include "BPP-Automation.js" // automation mode utilities
#include "BPP-Engine.js"     // stack engine
#include "BPP-GUI.js"        // GUI part

/*
 * Script entry point.
 * @param {boolean} fastMode - true if the script is running in fast mode.
 * @param {string} id - script identifier (e.g. "WBPP" or "FBPP").
 * @param {string} title - display title for the script.
 * @param {string} settingsKeyBase - base key for settings persistence.
 * @param {string} version - script version string.
 */
function BPPmain( fastMode, id, title, settingsKeyBase, version )
{
   // configure the engine with the flag for fast mode
   engine.id = id;
   engine.title = title;
   engine.version = version;
   engine.fastMode = fastMode;
   engine.loadSettingsKeyBase = settingsKeyBase;
   engine.saveSettingsKeyBase = settingsKeyBase;

   /**
    * Executes the main process.
    * @param {boolean} [testing] - true if the script is running in test mode.
    */
   function perform( testing )
   {
      try
      {
         console.show();

         let T = new ElapsedTime;

         // run
         engine.cleanProcessLog();
         engine.pipelineManager.initializeExecution();

         if ( runsInAutomationMode() )
            cout( "\n:LOGFILE:" + engine.logsFileName + ":LOGFILE:\n" );

         engine.pipelineManager.buildExecutionPipeline();
         engine.pipelineManager.runPipeline();
         engine.pipelineManager.postExecutionActions();

         if ( runsInAutomationMode() )
            if ( engine.operationQueue.interruptionRequested )
               if ( !engine.operationQueue.__interruptedFromTestCheckedScript__ )
                  cout( "\nTEST MANUALLY INTERRUPTED\n" );

         // complete the logging
         console.writeln( "<end><cbr><br>* " + engine.title + ": ", T.text );
         console.flush();

         // stop logging
         engine.consoleLogger.stopLogging();

         // show process logs
         if ( !engine.automationMode )
            engine.showProcessLogs();
      }
      catch ( x )
      {
         if ( !engine.automationMode )
            ( new MessageBox( x.message, engine.title + " " + engine.version, StdIcon.Error, StdButton.Ok ) ).execute();
         else if ( testing )
            cout( "\n" + x.message + "\nTEST FAILED" );
         else
            console.criticalln( x.message );
      }
      console.hide();
   }

   // save the current windows on the workspace
   let existingMainWindowIDs = ImageWindow.windows.filter( W => W.isWindow ).map( W => W.mainView.uniqueId );

   // check the execution mode
   if ( Parameters.isViewTarget )
      throw new Error( engine.title + " can only be executed in the global context." );

   // handles the automated mode
   let showDialog = true;
   if ( runsInAutomationMode() )
   {
      showDialog = false;
      console.noteln( ( fastMode ? "FBPP" : "WBPP" ) + " AUTOMATION MODE" );

      let doPerform = true;

      // resets the groups
      engine.groupsManager.clear();

      // enable automationMode and retrieve the test file
      engine.automationMode = true;

      let testFile = getTestFile();

      if ( testFile )
      {
         console.noteln( "testFile: ", testFile );
         cout( "\ntestFile: " + testFile )
         try
         {
            if ( File.exists( testFile ) )
            {
               let json = File.readTextFile( testFile );
               if ( json == undefined )
                  throw new Error( "Unable to read test file: " + testFile );

               // parse fileSearchRootPath before importing parameters
               parseFileSearchRootPath( engine );

               // load the parameters stored in the test file
               engine.testFile = testFile;
               engine.parametersManager.importParameters( json );

               // allow a subset of values to be overridden by the test configuration
               doPerform = parseTestModeOverrides( engine );
            }
            else
               throw new Error( "Test file not found: " + testFile );
         }
         catch ( x )
         {
            cout( "\n" + x.message + "\nTEST FAILED" );
            doPerform = false;
         }
      }
      else
      {
         console.noteln( "no testFile, parsing the command line options" );

         // parse command line parameters
         let result = parseCommandLineParameters( engine );
         doPerform = result.doPerform;

         engine.parametersManager.importParameters( false, result.dottedParams );
         engine.rebuild();

         // add file and dir from arguments
         parseFileParameters( engine );
      }

      // If we have to perform then we run WBPP and do not show the main dialog.
      // IF we do not perform then the main GUI is shown
      if ( doPerform )
         perform();
      else
         showDialog = true;
   }
   else
   {
      // hide the console and present the main GUI
      console.hide();
      engine.parametersManager.importParameters();

      // check if a previous running configuration exists and ask to reload in case
      if ( engine.parametersManager.hasRunningConfiguration() && !engine.fastMode )
      {
         let userChoice = ( new MessageBox( "A previous running configuration has been found. Do you want to reload it?",
            engine.title + " " + engine.version,
            StdIcon.Information,
            StdButton.Yes, StdButton.No ) ).execute();
         if ( userChoice == StdButton.Yes )
            engine.parametersManager.restoreRunningConfiguration();
      }
   }

   if ( showDialog )
   {

      for ( ;; )
      {
         let dialog = new StackDialog();
         dialog.updateControls();

         if ( !dialog.execute() )
            break;

         if ( engine.loadInWBPP )
         {
            // we're are here only if we clicked "open in WBPP" button

            // reconfigure the engine load the WBPP keeping the FBPP settings
            engine.id = BPP.Version.WBPP_ID;
            engine.title = BPP.Version.WBPP_TITLE;
            engine.version = BPP.Version.WBPP_VERSION;
            engine.fastMode = false;
            engine.parametersManager.saveSettings();
            engine.saveSettingsKeyBase = BPP.Version.WBPP_SETTINGS_KEY_BASE;
            engine.loadInWBPP = undefined;
            engine.pipelineManager.buildExecutionPipeline();
         }
         else
         {
            engine.diagnosticsManager.runDiagnostics();
            if ( !engine.diagnosticsManager.hasDiagnosticMessages() || engine.diagnosticsManager.showDiagnosticMessages( true /*cancelButton*/ ) )
               perform();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }

         CoreApplication.processEvents();
      }

      engine.parametersManager.removeRunningConfiguration();
      engine.parametersManager.saveSettings();
      engine = null;
   }

   // clean up residual image windows if needed
   ImageWindow.windows.filter( W => W.isWindow ).forEach( W =>
   {
      if ( existingMainWindowIDs.indexOf( W.mainView.uniqueId ) == -1 )
         W.forceClose();
   } );
}

// ----------------------------------------------------------------------------
// EOF BPP-Main.js - Released 2026-05-10T11:05:00Z
