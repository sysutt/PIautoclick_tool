// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-TestsRunner.js - Released 2026-05-10T11:05:00Z
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

#engine v8

#include "BPP-Global.js"
#include "BPP-Helper.js"

// Test status codes
var TEST_STATUS_READY = 0;
var TEST_STATUS_SUCCESS = 1;
var TEST_STATUS_FAILED = 2;
var TEST_STATUS_RUNNING = 3;

// Test runner messages
var MSG_TEST_FAILED = "TEST FAILED";
var MSG_TEST_EXECUTION_COMPLETED = "TEST EXECUTION COMPLETED";
var MSG_TEST_MANUALLY_INTERRUPTED = "TEST MANUALLY INTERRUPTED";
var MSG_TEST_EXECUTION_CRASHED = "Test execution crashed";
var MSG_FAILED_WHILE_RECORDING = "Failed while recording";
var MSG_PROCESS_START_TIMEOUT = "Process failed to start within timeout period";
var MSG_PROCESS_NOT_RUNNING = "Process failed to enter running state";
var MSG_TEST_TIMEOUT = "Test timed out after 2 hours";
var MSG_PROGRESS = "PROGRESS: ";

// Settings keys
var SETTINGS_KEY_BASE = "BatchPreprocessing/TestsRunner/";

// File extensions
var FILE_EXT_WBPP = "wbpptest";
var FILE_EXT_FBPP = "fbpptest";

// Script types
var SCRIPT_TYPE_WBPP = "WBPP";
var SCRIPT_TYPE_FBPP = "FBPP";

// Timeouts (in milliseconds)
var PROCESS_START_TIMEOUT_MS = 30000; // 30 seconds
var TEST_TIMEOUT_MS = 7200000; // 2 hours

/**
 * Main window dialog.
 *
 * @param {*} engine the WBPP test runner engine
 */
var WBPPTestRunnerDialog = class extends Dialog
{
   constructor( engine )
   {
      super();

   this.windowTitle = "BPP Tests Runner";

   // ===============
   // MAIN PARAMETERS
   // ===============

   this.currentNode = undefined; // the currently selected node
   this.waitingTest = false; // true when the GUI is monitoring the execution of a test and waiting it to complete

   // ==================
   // HANDLING FUNCTIONS
   // ==================

   /**
    * Redraws the GUI controls state, filling the list of trees and the directory locations.
    *
    */
   this.redraw = () =>
   {
      let tests = engine.tests;
      this.filesTreeBox.clear();

      let selectedIndex = this.currentNode && this.currentNode.__i__ || -1;

      for ( let i = 0; i < tests.length; i++ )
      {
         let test = tests[ i ];
         let node = new TreeBoxNode( this.filesTreeBox );

         node.setText( 0, test.filePath );
         node.checkable = true;
         node.checked = test.enabled;
         node.__test__ = test;
         node.__i__ = i;

         if ( selectedIndex == i )
         {
            node.selected = true;
            this.currentNode = node;
         }

         let scriptTypeIndex = 1;
         node.setText( scriptTypeIndex, test.script );

         let statusIndex = 2;
         switch ( test.status )
         {
            case engine.STATUS_READY:
               node.setIcon( statusIndex, this.scaledResource( ":/bullets/bullet-ball-glass-grey.png" ) );
               break;
            case engine.STATUS_SUCCESS:
               node.setIcon( statusIndex, this.scaledResource( ":/bullets/bullet-ball-glass-green.png" ) );
               break;
            case engine.STATUS_FAILED:
               node.setIcon( statusIndex, this.scaledResource( ":/icons/warning.png" ) );
               break;
            case engine.STATUS_RUNNING:
               node.setIcon( statusIndex, this.scaledResource( ":/icons/forward.png" ) );
               break;
         }

         let elapsedTimeIndex = 3;
         node.setText( elapsedTimeIndex, WBPPUtils.elapsedTimeToString( test.eta || 0 ) );

         let etaIndex = 4;
         if ( test.status == engine.STATUS_RUNNING )
            node.setText( etaIndex, test.progressInfo );
         else
            node.setText( etaIndex, test.notes );
      }

      for ( let i = 0; i < this.filesTreeBox.numberOfColumns; ++i )
         this.filesTreeBox.adjustColumnWidthToContents( i );

      // update the settings
      this.workingDirectoryEdit.text = engine.workingDirectory;
      this.sourcesDirectoryEdit.text = engine.sourcesDirectory;
      this.searchDirectoryEdit.text = engine.fileSearchRootPath;
      this.executableEdit.text = engine.executable;
      this.testCheckerScriptEdit.text = engine.testCheckerScript;
      this.keepPIOpenCheckBox.checked = engine.keepPIOpen;
      this.updateNotes();
      CoreApplication.processEvents();
   };

   /**
    * Updates the state of the GUI depending on the running state.
    *
    * @param {*} running
    */
   this.setRunningStatus = ( running ) =>
   {
      let enabled = !running;
      this.workingFolderButton.enabled = enabled;
      this.workingDirectoryEdit.enabled = enabled;
      this.sourcesDirectoryButton.enabled = enabled;
      this.sourcesDirectoryEdit.enabled = enabled;
      this.searchDirectoryButton.enabled = enabled;
      this.searchDirectoryEdit.enabled = enabled;
      this.executableButton.enabled = enabled;
      this.executableEdit.enabled = enabled;
      this.testCheckerScriptButton.enabled = enabled;
      this.testCheckerScriptEdit.enabled = enabled;

      this.addFolderButton.enabled = enabled;
      this.reloadAllButton.enabled = enabled;
      this.clearButton.enabled = enabled;
      this.runAllButton.enabled = enabled;
      this.runFailedButton.enabled = enabled;
      this.resetStatusButton.enabled = enabled;
      this.loadButton.enabled = enabled;
      this.runSelectedButton.enabled = enabled;
      this.resetButton.enabled = enabled;
   };

   /**
    * Launches a test in a separate PixInsight instance. Optionally, the test can be launched with
    * the instruction to close the PixInsight instance once the test is terminated and to load the
    * test only without running it.
    *
    * @param {*} test
    * @param {*} terminatePIOnComplete
    * @param {*} loadOnly
    * @param {*} recordTest true if the test must be executed and recorded
    * @return {*}
    */
   this.runTest = ( test, terminatePIOnComplete, loadOnly, recordTest ) =>
   {
      try
      {
         engine.prepareTestForExecution( test );
         this.redraw();
         terminatePIOnComplete = terminatePIOnComplete == undefined ? true : terminatePIOnComplete;
         loadOnly = loadOnly == undefined ? false : loadOnly;

         // Get platform-specific parameters
         let parameters = [ "-n" ];
         if ( terminatePIOnComplete )
            parameters.push( "--force-exit" );
         parameters.push( "--automation-mode" );

         // Build the common parameters for all platforms
         parameters.push(
            "-r=\""
            + engine.sourcesDirectory
            + ( test.script == "WBPP"
               ? "/src/scripts/BatchPreprocessing/WBPP.js,automationMode=true,testFile="
               : "/src/scripts/BatchPreprocessing/FBPP.js,automationMode=true,testFile="
            )
            + test.filePath
            + ",outputDir="
            + engine.workingDirectory
            + ",fileSearchRootPath=" + engine.fileSearchRootPath
            + ",usePipelineScript=true,pipelineScriptFile="
            + engine.testCheckerScript
            + ( loadOnly ? ",loadOnly" : "" )
            + ( recordTest ? ",recordTest" : "" )
            + "\"" );

         console.noteln( "=== test command ===" );
         console.writeln( engine.executable );
         console.writeln( engine.executable + " " + parameters.join( " " ) );
         console.noteln( "====================" );

         if ( !loadOnly )
            test.status = engine.STATUS_RUNNING;
         test.recording = recordTest;
         let process = new ExternalProcess();
         process.__command__ = engine.executable + " " + parameters.join( " " );

         process.start( engine.executable, parameters );
         return process;
      }
      catch ( error )
      {
         console.criticalln( "Failed to run test:", error.toString() );
         test.status = engine.STATUS_FAILED;
         test.notes = "Failed to launch test: " + error.toString();
         this.redraw();
         return null;
      }
   };

   /**
    * Waits for a test to terminate. This function monitors the execution status of the given process
    * and interpret the information printed to its cout stream to gather information about the
    * current execution and the results.
    *
    * @param {*} process
    * @param {*} test
    */
   this.waitTest = ( process, test ) =>
   {
      const startTime = Date.now();

      let updateConsole = function( msg )
      {
         console.clear();
         console.noteln( "=== test command ===" );
         console.writeln( process.__command__ );
         console.noteln( "====================" );
         console.writeln();
         if ( msg )
         {
            console.noteln( msg );
         }
      };

      updateConsole();
      this.waitingTest = true;
      this.setRunningStatus( true );

      let buffer = {
         stdout: "",
         stderr: ""
      };
      test.cout = "";

      // Wait for process to start
      while ( process.isStarting )
      {
         if ( Date.now() - startTime > PROCESS_START_TIMEOUT_MS )
         {
            process.terminate();
            test.status = engine.STATUS_FAILED;
            test.notes = MSG_PROCESS_START_TIMEOUT;
            this.redraw();
            return;
         }
         CoreApplication.processEvents();
         sleep( 1 );
      }

      // Check if process entered running state
      if ( !process.isRunning )
      {
         test.status = engine.STATUS_FAILED;
         test.notes = MSG_PROCESS_NOT_RUNNING;
         this.redraw();
         return;
      }

      // Monitor running process
      while ( process.isRunning )
      {
         // Check for timeout
         if ( Date.now() - startTime > TEST_TIMEOUT_MS )
         {
            process.terminate();
            test.status = engine.STATUS_FAILED;
            test.notes = MSG_TEST_TIMEOUT;
            this.redraw();
            return;
         }

         // Update the progress information
         buffer.stdout += process.stdout.toString();
         buffer.stderr += process.stderr.toString();

         if ( buffer.stdout != test.cout )
         {
            test.cout = buffer.stdout;
            updateConsole( test.cout );
         }

         let strings = test.cout.split( "\n" );
         for ( let i = strings.length - 1; i >= 0; i-- )
         {
            if ( strings[ i ].indexOf( MSG_PROGRESS ) != -1 )
            {
               test.progressInfo = strings[ i ];
               break;
            }
         }
         this.redraw();
         CoreApplication.processEvents();
         sleep( 1 );
      }

      // Capture any remaining output
      buffer.stdout += process.stdout.toString();
      buffer.stderr += process.stderr.toString();
      test.cout = buffer.stdout;
      test.progressInfo = "";

      // Update console with final output
      updateConsole( test.cout );

      // Keep raw cout for parsing before HTML conversion
      let rawCout = test.cout;
      // Strip :LOGFILE: markers from display output
      test.cout = test.cout.replace( /:LOGFILE:.*:LOGFILE:/g, "" );

      function saveLogs( test )
      {
         let test_fname = File.extractNameAndExtension( test.filePath );
         let srcLog = WBPPUtils.smartNaming.lastMatching( rawCout, /:LOGFILE:.*:LOGFILE:/g );
         srcLog = srcLog && srcLog.replace( /:LOGFILE:/g, "" );
         console.noteln( "test log file: <raw>" + srcLog + "</raw>" );
         if ( srcLog && File.exists( srcLog ) )
         {
            let destLog = engine.workingDirectory + "/" + test_fname + ".log";
            if ( File.exists( destLog ) )
               File.remove( destLog );
            console.noteln( "copy to: <raw>" + destLog + "</raw>" );
            File.copyFile( destLog, srcLog );
            test.logFile = destLog;
         }
      }

      if ( rawCout.indexOf( MSG_TEST_EXECUTION_COMPLETED ) == -1 )
      {
         // if this is not present then the execution didn't complete
         test.status = engine.STATUS_FAILED;
         test.notes = MSG_TEST_EXECUTION_CRASHED;
         saveLogs( test );
      }
      else if ( rawCout.indexOf( MSG_TEST_MANUALLY_INTERRUPTED ) != -1 )
      {
         // if this is present then the test was manually interrupted
         test.status = engine.STATUS_READY;
         test.notes = MSG_TEST_MANUALLY_INTERRUPTED;
         saveLogs( test );
      }
      else if ( rawCout.indexOf( MSG_TEST_FAILED ) != -1 )
      {
         // a test has failed
         test.status = engine.STATUS_FAILED;
         test.notes = test.recording ? MSG_FAILED_WHILE_RECORDING : MSG_TEST_FAILED;
         saveLogs( test );
      }
      else
      {
         test.status = engine.STATUS_SUCCESS;
         test.notes = "";
         saveLogs( test );
         // Store execution time for successful tests
         test.eta = ( Date.now() - startTime ) / 1000;
      }
      test.recording = false;
      this.setRunningStatus( false );
      this.redraw();
   };

   //

   this.updateNotes = () =>
   {
      let content = ( this.currentNode && this.currentNode.__test__ && this.currentNode.__test__.cout || "" ).split( "\n" ).join( "<br>" )
      let info = "<HTML><style>"
         + "body { font-family: DejaVu Sans Mono, Monospace; font-size: 10pt; background: #FFFFFF; border-style: solid; border-color: #777777; border-width: 0pt;}"
         + "</style><body><div style=\"margin: 4pt;\">" + content + "</div></body></HTML>";
      this.coutView.setHTML( info );
   };

   // ================
   // GUI CONSTRUCTION
   // ================

   this.filesTreeBox = new TreeBox( this );
   this.filesTreeBox.setScaledMinWidth( 800 );
   this.filesTreeBox.setScaledMinHeight( 400 );
   this.filesTreeBox.headerVisible = true;
   this.filesTreeBox.headerSorting = false;
   this.filesTreeBox.numberOfColumns = 5;
   this.filesTreeBox.setHeaderText( 0, "File" );
   this.filesTreeBox.setHeaderText( 1, "Script" );
   this.filesTreeBox.setHeaderText( 2, "Status" );
   this.filesTreeBox.setHeaderText( 3, "ETA" );
   this.filesTreeBox.setHeaderText( 4, "Note" );

   this.filesTreeBox.onNodeSelectionUpdated = () =>
   {
      if ( this.filesTreeBox.selectedNodes.length > 0 )
      {
         this.currentNode = this.filesTreeBox.selectedNodes[ 0 ];
      }
      this.updateNotes();
   };

   this.filesTreeBox.onNodeUpdated = ( node, column ) =>
   {
      if ( column != 0 )
         return;
      let i = this.filesTreeBox.childIndex( node );
      engine.tests[ i ].enabled = node.checked;
   };

   //

   this.coutView = new WebView( this );
   this.coutView.useRichText = true;
   this.coutView.setScaledMinHeight( 200 );

   //

   this.reloadAllButton = new PushButton( this );
   this.reloadAllButton.text = "Reload tests";
   this.reloadAllButton.toolTip = "<p>Reload all tests.</p>";

   this.reloadAllButton.onClick = () =>
   {
      engine.reload();
      this.redraw();
   };

   //

   this.addTestButton = new PushButton( this );
   this.addTestButton.text = "Add Test";
   this.addTestButton.icon = this.scaledResource( ":/icons/add.png" );
   this.addTestButton.toolTip = "<p>Adds a test to the list.</p>";

   this.addTestButton.onClick = () =>
   {
      let ofd = new OpenFileDialog;
      ofd.caption = "Add a BPP test";
      ofd.filters = [
         [ "BPP tests", FILE_EXT_WBPP, FILE_EXT_FBPP ]
      ];
      if ( ofd.execute() )
      {
         engine.addTestFile( ofd.filePath );
         engine.sort();
         this.redraw();
      }
   };

   //

   this.addFolderButton = new PushButton( this );
   this.addFolderButton.text = "Directory";
   this.addFolderButton.icon = this.scaledResource( ":/icons/add.png" );
   this.addFolderButton.toolTip = "<p>Load all tests from a selected folder.</p>";

   this.addFolderButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.caption = "Select Root Directory";
      if ( gdd.execute() )
      {
         let rootDir = gdd.directoryPath;
         let filters = [ FILE_EXT_WBPP, FILE_EXT_FBPP ];
         let L = new FileList( rootDir, filters, false /*verbose*/ );
         L.files.forEach( ( filePath ) =>
         {
            engine.addTestFile( filePath );
         } );
         engine.sort();
         this.redraw();
      }
   };

   //

   this.clearButton = new PushButton( this );
   this.clearButton.text = "Clear list";
   this.clearButton.icon = this.scaledResource( ":/browser/delete-multiple.png" );
   this.clearButton.toolTip = "<p>Clear all tests</p>";
   this.clearButton.onMousePress = () =>
   {
      engine.clear();
      this.redraw();
   };

   //

   this.resetStatusButton = new PushButton( this );
   this.resetStatusButton.text = "Reset results";
   this.resetStatusButton.toolTip = "<p>Resets the tests status</p>";
   this.resetStatusButton.onMousePress = () =>
   {
      engine.prepareForExecution();
      this.redraw();
   };

   //

   this.runAllButton = new PushButton( this );
   this.runAllButton.text = "Run all";
   this.runAllButton.toolTip = "<p>Run all active tests</p>";
   this.runAllButton.onMousePress = () =>
   {
      engine.prepareForExecution();
      this.redraw();
      let testsToRun = engine.activeTests();

      // Loop through tests and run each one in background
      for ( let i = 0; i < testsToRun.length; i++ )
      {
         engine.clearWorkingDirectory();
         let process = this.runTest( testsToRun[ i ] );
         if ( process )
         {
            this.waitTest( process, testsToRun[ i ] );
         }
         else
         {
            // Process failed to start, test status is already set to failed in runTest
            this.redraw();
         }
      }
   };

   //

   this.runSelectedButton = new PushButton( this );
   this.runSelectedButton.text = "Run selected";
   this.runSelectedButton.toolTip = "<p>Launch the selected test without monitoring result</p>";
   this.runSelectedButton.onMousePress = () =>
   {
      if ( this.currentNode )
      {
         engine.prepareTestForExecution( this.currentNode.__test__ );
         this.redraw();
         let process = this.runTest( this.currentNode.__test__, !engine.keepPIOpen /* close PI when completed  */ );
         if ( process )
         {
            this.waitTest( process, this.currentNode.__test__ );
         }
         else
         {
            // Process failed to start, test status is already set to failed in runTest
            this.redraw();
         }
      }
   };

   //

   this.runFailedButton = new PushButton( this );
   this.runFailedButton.text = "Run failed";
   this.runFailedButton.toolTip = "<p>Run all tests that are not in success status (failed or not yet run)</p>";
   this.runFailedButton.onMousePress = () =>
   {
      let testsToRun = engine.activeTests().filter( t => t.status != engine.STATUS_SUCCESS );
      for ( let i = 0; i < testsToRun.length; i++ )
      {
         engine.prepareTestForExecution( testsToRun[ i ] );
         engine.clearWorkingDirectory();
         let process = this.runTest( testsToRun[ i ] );
         if ( process )
         {
            this.waitTest( process, testsToRun[ i ] );
         }
         else
         {
            this.redraw();
         }
      }
   };

   //

   this.recordAllButton = new PushButton( this );
   this.recordAllButton.text = "Record all";
   this.recordAllButton.toolTip = "<p>Run all active tests</p>";
   this.recordAllButton.onMousePress = () =>
   {
      engine.prepareForExecution();
      this.redraw();
      let testsToRun = engine.activeTests();

      // Loop through tests and run each one in background
      for ( let i = 0; i < testsToRun.length; i++ )
      {
         engine.clearWorkingDirectory();
         let process = this.runTest( testsToRun[ i ], true /* close PI when completed  */ , false /* load only */ , true /* record */ );
         if ( process )
         {
            this.waitTest( process, testsToRun[ i ] );
         }
         else
         {
            // Process failed to start, test status is already set to failed in runTest
            this.redraw();
         }
      }
   };

   //

   this.recordSelectedButton = new PushButton( this );
   this.recordSelectedButton.text = "Record selected";
   this.recordSelectedButton.toolTip = "<p>Launch the selected test without monitoring result</p>";
   this.recordSelectedButton.onMousePress = () =>
   {
      if ( this.currentNode )
      {
         engine.prepareTestForExecution( this.currentNode.__test__ );
         this.redraw();
         let process = this.runTest( this.currentNode.__test__, !engine.keepPIOpen /* close PI when completed  */ , false /* load only */ , true /* record */ );
         if ( process )
         {
            this.waitTest( process, this.currentNode.__test__ );
         }
         else
         {
            // Process failed to start, test status is already set to failed in runTest
            this.redraw();
         }
      }
   };

   //

   this.loadButton = new PushButton( this );
   this.loadButton.text = "Load selected";
   this.loadButton.toolTip = "<p>Opens a PixInsight instance loading the test</p>";
   this.loadButton.onMousePress = () =>
   {
      if ( this.currentNode )
      {
         engine.prepareTestForExecution( this.currentNode.__test__ );
         this.redraw();
         this.runTest( this.currentNode.__test__, false /* close PI when completed  */ , true /* load only */ );
      }
   };

   //

   this.openLogsButton = new PushButton( this );
   this.openLogsButton.text = "Open logs";
   this.openLogsButton.toolTip = "<p>Opens the log file for the test</p>";
   this.openLogsButton.onMousePress = () =>
   {
      if ( this.currentNode && this.currentNode.__test__.logFile && this.currentNode.__test__.logFile.length > 0 )
      {
         let vscode = new ExternalProcess();
         vscode.start( "code", [ this.currentNode.__test__.logFile ] );
      }
   };

   //

   this.keepPIOpenCheckBox = new CheckBox( this );
   this.keepPIOpenCheckBox.text = "Keep PI open"
   this.keepPIOpenCheckBox.onCheck = ( checked ) =>
   {
      engine.keepPIOpen = checked;
      this.redraw();
   };

   //

   this.resetButton = new PushButton( this );
   this.resetButton.text = "Reset";
   this.resetButton.icon = this.scaledResource( ":/icons/reload.png" );
   this.resetButton.toolTip = "<p>Perform optional reset and clearing actions.</p>";
   this.resetButton.onClick = () =>
   {
      engine.defaults();
      this.redraw();
   };

   // ---------- PARAMETERS

   let buttonsSizer = new VerticalSizer;
   buttonsSizer.spacing = 6;
   let editSizer = new VerticalSizer;
   editSizer.spacing = 6;

   //

   this.workingFolderButton = new PushButton( this );
   this.workingFolderButton.text = "Working Directory";
   this.workingFolderButton.toolTip = "<p>Select the working directory.</p>";
   this.workingFolderButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.caption = "Select Root Directory";
      if ( gdd.execute() )
      {
         engine.workingDirectory = gdd.directoryPath;
         this.redraw();
      }
   };

   this.workingDirectoryEdit = new Edit( this );
   this.workingDirectoryEdit.toolTip = "<p>The working directory.</p>";

   buttonsSizer.add( this.workingFolderButton );
   editSizer.add( this.workingDirectoryEdit );

   //

   this.sourcesDirectoryButton = new PushButton( this );
   this.sourcesDirectoryButton.text = "Sources Directory";
   this.sourcesDirectoryButton.toolTip = "<p>Select the sources directory.</p>";
   this.sourcesDirectoryButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.caption = "Select the sources directory";
      if ( gdd.execute() )
      {
         engine.sourcesDirectory = gdd.directoryPath;
         this.redraw();
      }
   };

   this.sourcesDirectoryEdit = new Edit( this );
   this.sourcesDirectoryEdit.toolTip = "<p>The sources directory.</p>";

   buttonsSizer.add( this.sourcesDirectoryButton );
   editSizer.add( this.sourcesDirectoryEdit );

   //

   this.searchDirectoryButton = new PushButton( this );
   this.searchDirectoryButton.text = "Search Directory";
   this.searchDirectoryButton.toolTip = "<p>Defines an alternative directory path to be used to search for test files.</p>";
   this.searchDirectoryButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.caption = "Select the search directory root";
      if ( gdd.execute() )
      {
         engine.fileSearchRootPath = gdd.directoryPath;
         this.redraw();
      }
   };

   this.searchDirectoryEdit = new Edit( this );
   this.searchDirectoryEdit.toolTip = "<p>Defines an alternative directory path to be used to search for test files.</p>";

   buttonsSizer.add( this.searchDirectoryButton );
   editSizer.add( this.searchDirectoryEdit );

   //

   this.executableButton = new PushButton( this );
   this.executableButton.text = "Executable";
   this.executableButton.toolTip = "<p>Select the pixinsight executable.</p>";
   this.executableButton.onClick = () =>
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = false;
      ofd.caption = "Select the PixInsight executable file";
      if ( ofd.execute() )
      {
         engine.executable = ofd.filePath;
         this.redraw();
      }
   };

   this.executableEdit = new Edit( this );
   this.executableEdit.toolTip = "<p>The PixIsnight executable file.</p>";

   buttonsSizer.add( this.executableButton );
   editSizer.add( this.executableEdit );

   //

   this.testCheckerScriptButton = new PushButton( this );
   this.testCheckerScriptButton.text = "Test checker script";
   this.testCheckerScriptButton.toolTip = "<p>Select the test checker script.</p>";
   this.testCheckerScriptButton.onClick = () =>
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = false;
      ofd.caption = "Select the test checked script";
      ofd.filters = [
         [ "Javascript", ".js" ]
      ];
      if ( ofd.execute() )
      {
         engine.testCheckerScript = ofd.filePath;
         this.redraw();
      }
   };

   this.testCheckerScriptEdit = new Edit( this );
   this.testCheckerScriptEdit.toolTip = "<p>The test checker pipeline script.</p>";

   buttonsSizer.add( this.testCheckerScriptButton );
   editSizer.add( this.testCheckerScriptEdit );

   // LAYOUT

   this.parametersSizer = new HorizontalSizer;
   this.parametersSizer.spacing = 6;
   this.parametersSizer.add( buttonsSizer );
   this.parametersSizer.add( editSizer );

   //
   let vSpacing = 20;
   this.controlsSizer = new VerticalSizer;
   this.controlsSizer.spacing = 6;
   // --- Test management ---
   this.controlsSizer.add( this.addTestButton );
   this.controlsSizer.add( this.addFolderButton );
   this.controlsSizer.add( this.reloadAllButton );
   this.controlsSizer.add( this.clearButton );
   this.controlsSizer.addSpacing( vSpacing );
   // --- Execution ---
   this.controlsSizer.add( this.runSelectedButton );
   this.controlsSizer.add( this.runAllButton );
   this.controlsSizer.add( this.runFailedButton );
   this.controlsSizer.add( this.resetStatusButton );
   this.controlsSizer.addSpacing( vSpacing );
   // --- Record & Load ---
   this.controlsSizer.add( this.loadButton );
   this.controlsSizer.add( this.recordSelectedButton );
   this.controlsSizer.add( this.recordAllButton );
   this.controlsSizer.add( this.keepPIOpenCheckBox );
   this.controlsSizer.addSpacing( vSpacing );
   this.controlsSizer.add( this.openLogsButton );
   this.controlsSizer.addStretch();
   this.controlsSizer.add( this.resetButton );


   //

   this.leftSizer = new VerticalSizer;
   this.leftSizer.spacing = 6;
   this.leftSizer.add( this.filesTreeBox );
   this.leftSizer.add( this.coutView );

   //

   this.treeAndControlSizer = new HorizontalSizer;
   this.treeAndControlSizer.spacing = 6;
   this.treeAndControlSizer.add( this.leftSizer );
   this.treeAndControlSizer.add( this.controlsSizer );

   //

   this.sizer = new VerticalSizer;
   this.sizer.spacing = 6;
   this.sizer.margin = 6;
   this.sizer.add( this.parametersSizer );
   this.sizer.add( this.treeAndControlSizer );

      this.redraw();
   }
}

/**
 * The WBPP test runner engine.
 *
 */
var WBPPTestRunnerEngine = class
{
   constructor()
   {
      // STATUS codes
      this.STATUS_READY = TEST_STATUS_READY;
      this.STATUS_SUCCESS = TEST_STATUS_SUCCESS;
      this.STATUS_FAILED = TEST_STATUS_FAILED;
      this.STATUS_RUNNING = TEST_STATUS_RUNNING;

      this.keepPIOpen = false;

      // defaults management
      this.defaults = () =>
      {
         // set the initial working directory
         this.workingDirectory = File.currentWorkingDirectory;

         // set the initial sources folder
         this.sourcesDirectory = CoreApplication.srcDirPath;

         // sers the default serach directory as empty
         this.fileSearchRootPath = "";

         // set the initial executable file path
         if ( System.platform == "Linux" )
            this.executable = CoreApplication.filePath + ".sh";
         else
            this.executable = CoreApplication.filePath;

         // set the initial test checked script path
         this.testCheckerScript = CoreApplication.srcDirPath + "/scripts/BatchPreprocessing/BPP-testChecker.js";
      };

      this.defaults();

      this.addTestFile = ( filePath ) =>
      {
         try
         {
            let data = JSON.parse( File.readTextFile( filePath ) );
            if ( data != undefined )
            {
               let test = {
                  filePath: filePath,
                  logFile: "",
                  content: data,
                  eta: (() => {
                     try {
                        let tes = data.data && data.data.testExecutionStatus;
                        if ( typeof tes === "string" ) tes = JSON.parse( tes );
                        return tes && tes.totalExecutionTime || 0;
                     } catch( e ) { return 0; }
                  })(),
                  enabled: true,
                  status: this.STATUS_READY,
                  recording: false,
                  cout: "",
                  notes: "",
                  progressInfo: "",
                  script: filePath.indexOf( FILE_EXT_WBPP ) != -1 ? SCRIPT_TYPE_WBPP : SCRIPT_TYPE_FBPP
               };
               this.tests.push( test );
            }
         }
         catch ( e )
         {
            console.warningln( "Error loading test file: <raw>" + filePath, "</raw>: ", e );
         }
      };

      this.activeTests = () =>
      {
         return this.tests.filter( t => t.enabled );
      };

      this.prepareTestForExecution = ( test ) =>
      {
         test.status = this.STATUS_READY;
         test.notes = "";
         test.progressInfo = "";
         test.cout = "";
         test.logFile = "";
         test.recording = false;
      };

      this.prepareForExecution = () =>
      {
         this.tests.forEach( t =>
         {
            this.prepareTestForExecution( t );
         } );
      };

      this.clear = () =>
      {
         this.tests = [];
      };

      this.sort = () =>
      {
         this.tests.sort( ( a, b ) =>
         {
            return a.filePath.localeCompare( b.filePath );
         } );
      };

      this.clearWorkingDirectory = () =>
      {
         let foldersToRemove = [
            "logs", "calibrated", "debayered", "cosmetized", "measured", "ldd_lps", "registered", "master"
         ];
         for ( let i = 0; i < foldersToRemove.length; i++ )
         {
            let path = this.workingDirectory + "/" + foldersToRemove[ i ];
            if ( File.directoryExists( path ) )
            {
               console.noteln( "Deleting the working subfolder <raw>" + path + "</raw>" );
               removeDirectoryAndContent( path );
            }
         }
      };

      this.reload = () =>
      {
         let fnames = this.tests.map( t => t.filePath );
         this.clear();
         fnames.forEach( fname => this.addTestFile( fname ) );
      };

      this.load = () =>
      {
         function load( key, type )
         {
            return Settings.read( SETTINGS_KEY_BASE + key, type );
         }
         let o;
         if ( ( o = load( "workingDirectory", DataType.UTF8String ) ) != null )
            this.workingDirectory = o;
         if ( ( o = load( "sourcesDirectory", DataType.UTF8String ) ) != null )
            this.sourcesDirectory = o;
         if ( ( o = load( "fileSearchRootPath", DataType.UTF8String ) ) != null )
            this.fileSearchRootPath = o;
         if ( ( o = load( "executable", DataType.UTF8String ) ) != null )
            this.executable = o;
         if ( ( o = load( "testCheckerScript", DataType.UTF8String ) ) != null )
            this.testCheckerScript = o;
         if ( ( o = load( "keepPIOpen", DataType.Boolean ) ) != null )
            this.keepPIOpen = o;
         if ( ( o = load( "tests", DataType.UTF8String ) ) != null )
         {
            o = JSON.parse( o );
            if ( o != undefined )
            {
               this.tests = o;
            }
         }
      };

      this.save = () =>
      {
         function save( key, type, value )
         {
            try
            {
               Settings.write( SETTINGS_KEY_BASE + key, type, value );
            }
            catch ( e )
            {
               console.warningln( "Unable to save [", key, "] for type ", type, " with value ", value );
            }
         }

         save( "workingDirectory", DataType.UTF8String, this.workingDirectory );
         save( "sourcesDirectory", DataType.UTF8String, this.sourcesDirectory );
         save( "fileSearchRootPath", DataType.UTF8String, this.fileSearchRootPath );
         save( "executable", DataType.UTF8String, this.executable );
         save( "testCheckerScript", DataType.UTF8String, this.testCheckerScript );
         save( "keepPIOpen", DataType.Boolean, this.keepPIOpen );
         save( "tests", DataType.UTF8String, JSON.stringify( this.tests ) );
      };

      this.clear();
   }
};

// scoped execution
{
   let wbppTestRunnerEngine = new WBPPTestRunnerEngine();

   wbppTestRunnerEngine.load();
   let dialog = new WBPPTestRunnerDialog( wbppTestRunnerEngine );
   dialog.execute();
   wbppTestRunnerEngine.save();
}

// ----------------------------------------------------------------------------
// EOF BPP-TestsRunner.js - Released 2026-05-10T11:05:00Z
