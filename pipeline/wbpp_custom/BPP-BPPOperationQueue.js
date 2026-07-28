// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-BPPOperationQueue.js - Released 2026-05-10T11:05:00Z
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
 * BPP operation queue extending the base OperationQueue with execution
 * monitoring, timer-based progress updates, and execution report tracking.
 */
var BPPOperationQueue = class extends OperationQueue
{
   constructor()
   {
      super();

      // refresh timer
      this.updaterTimer = new Timer
      this.updaterTimer.interval = 1;
      this.updaterTimer.periodic = true;
      this.updaterTimer.dialog = this;
      this.updaterTimer.onTimeout = () =>
      {
         if ( this.executionMonitorDialog )
         {
            this.executionMonitorDialog.updateRunningOperation( this.trackableOperations() );
            this.executionMonitorDialog.noteLabel.text = "Elapsed: " + WBPPUtils.elapsedTimeToString( this.elapsed.value );
         }
         // refresh the progress report
         CoreApplication.processEvents();
      };
      this.updaterTimer.stop();
   }

   /**
    * Handles the pipeline termination request by interrupting the queue
    * and aborting the console.
    */
   onTerminationRequest = () =>
   {
      this.requestInterruption();
      console.abort( true /* don't ask */ );
   };

   /**
    * Callback invoked after each operation step. Manages the execution monitor
    * dialog lifecycle: creates it when the queue starts running, dismisses it
    * when the queue becomes inactive, and refreshes the execution report.
    */
   stepCallback = () =>
   {
      switch ( this.status )
      {
         case OperationQueueStatus.RUNNING:
            if ( !this.currentOperation() || this.executionMonitorDialog == undefined )
            {
               // INITIALIZED, READY TO RUN THE FIRST OPERATION
               // show the monitor view and start the refresh timer
               this.executionMonitorDialog = new ExecutionMonitorDialog( false /* as report */ , this.requestInterruption, undefined /* operations */ , this.onTerminationRequest );
               this.executionMonitorDialog.show();
               this.updateExecutionReport();
               this.executionMonitorDialog.adjustDialogFrame();
               // start the event and GUI refresh timer
               this.updaterTimer.start();
            }
            // flush the logs
            engine.consoleLogger.flush();
            break;

         case OperationQueueStatus.INACTIVE:
            // EXECUTION COMPLETED, dismiss the execution monitor as tracker and show it as report
            this.updaterTimer.stop();
            this.hideExecutionMonitorDialog();
            // remove the temporary saved parameters
            engine.parametersManager.removeRunningConfiguration();

            // if we are in automation mode and
            //   - not on "LoadOnly"
            //   - not recording the test
            // return;
            if ( engine.automationMode && !engine.testLoadOnly && !engine.recordTest )
               return;

            // store the execution status to be eventually saved in the test export information
            engine.executionStatus = this.getExecutionStatus();

            // in fast mode we always clear the cache
            if ( engine.fastMode )
               engine.executionCache.reset();

            // export the resulting test (with no cache) if we're recording
            if ( engine.automationMode && engine.recordTest && engine.testFile )
            {
               console.noteln( "STORE RECORDED TEST INTO ", engine.testFile )
               engine.executionCache.reset();
               let json = engine.parametersManager.exportParameters( true /* toJson */ );
               if ( File.exists( engine.testFile ) )
                  File.remove( engine.testFile );
               File.writeTextFile( engine.testFile, json );
               return;
            }

            this.executionMonitorDialog = new ExecutionMonitorDialog( true /* as report */ , undefined /* request interruption callback */ , this.trackableOperations() );
            this.executionMonitorDialog.noteLabel.text = "Executed in " + WBPPUtils.elapsedTimeToString( this.executionTime );

            // blocking execution
            this.executionMonitorDialog.execute();
            break;
      }
      // refresh the execution report after each step
      this.updateExecutionReport();
   };

   /**
    * Returns the list of trackable operations from the queue.
    *
    * @returns {Array<OperationBlock>} Filtered list of trackable operations
    */
   trackableOperations = () =>
   {
      return this.operations.filter( item => ( item.operation.trackable || false ) ).map( item => item.operation )
   };

   /**
    * This function saves the current pipeline status.
    * This information is handled by the test saving operation.
    */
   getExecutionStatus()
   {
      let executionStatus = {
         totalExecutionTime: this.executionTime,
         ops: []
      };

      for ( let i = 0; i < this.operations.length; ++i )
      {
         if ( this.operations[ i ].operation.trackable )
         {
            executionStatus.ops[ i ] = {};
            executionStatus.ops[ i ].operation = this.operations[ i ].operation;
            executionStatus.ops[ i ].name = this.operations[ i ].operation.name;
         }
      }

      return executionStatus;
   }

   /**
    * Refreshes the execution monitor dialog with the current trackable operations.
    */
   updateExecutionReport()
   {
      if ( this.executionMonitorDialog )
         this.executionMonitorDialog.updateWithOperations( this.trackableOperations() );
   }

   /**
    * Dismisses and cleans up the execution monitor dialog and any pending
    * message box, setting both references to undefined.
    */
   hideExecutionMonitorDialog()
   {
      // execution dialog
      if ( this.executionMonitorDialog )
      {
         this.executionMonitorDialog.ok();
         this.executionMonitorDialog = undefined;
      }
      // step termination box
      if ( this.waitingMsgBox )
      {
         this.waitingMsgBox.ok();
         this.waitingMsgBox = undefined;
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-BPPOperationQueue.js - Released 2026-05-10T11:05:00Z
