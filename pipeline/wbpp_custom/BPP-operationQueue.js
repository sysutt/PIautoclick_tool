// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-OperationQueue.js - Released 2026-05-10T11:05:00Z
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
 * Enumeration of possible operation queue states.
 * @enum {number}
 */
var OperationQueueStatus = {
   INACTIVE: 0, // Queue is not processing any operations
   RUNNING: 1 // Queue is actively processing operations
};

/**
 * Enumeration of possible operation block states.
 * @enum {number}
 */
var OperationBlockStatus = {
   READY: 0, // Operation is ready to be executed
   RUNNING: 1, // Operation is currently executing
   DONE: 2, // Operation has completed successfully
   FAILED: 3, // Operation encountered an error during execution
   CANCELED: 4 // Operation was canceled before or during execution
};

/**
 * Represents an operation block that can be queued in an OperationQueue.
 * This is an abstract base class that should be extended by concrete operation implementations.
 * Subclasses must implement the run() method to define the actual operation behavior.
 *
 * @class
 * @abstract
 */
var OperationBlock = class
{

   constructor()
   {
      /** @type {number} Current status of the operation block */
      this.status = OperationBlockStatus.READY;

      /** @type {boolean} Whether this operation block triggers event script execution */
      this.triggersEventScript = false;

      /** @type {ElapsedTime} Timer for measuring operation execution duration */
      this.elapsed = new ElapsedTime;

      /** @type {number} Total execution time after operation completion */
      this.executionTime = 0;
   }

   /**
    * Internal method to execute the operation safely with error handling and timing.
    * This method should not be called directly - use the OperationQueue to execute operations.
    *
    * @protected
    * @param {Object} environment The shared environment object containing operation context
    * @param {Function} interruptQueue Callback to request queue interruption
    * @returns {void}
    */
   _perform( environment, interruptQueue )
   {
      this.elapsed.reset();
      this.executionTime = 0;
      // safely handle the operation execution
      try
      {
         let status = this.run( environment, interruptQueue )
         this.status = status != undefined ? status : OperationBlockStatus.DONE;
      }
      catch ( e )
      {
         console.warningln( "Operation queue error: ", e instanceof Error ? e.message : String( e ) );
         console.warningln( "Operation queue error stack: ", e instanceof Error ? e.stack : "(no stack)" );
         // a critical error occurred, mark the operation as failed and return
         this.status = OperationBlockStatus.FAILED;
         return;
      }
      this.executionTime = this.elapsed.value;
   }
}

/**
 * Operation Queue. This object handles the serial execution of queued operational tasks.
 * It provides functionality for adding, managing, and executing operations in sequence,
 * with support for event handling and interruption.
 *
 * @class
 */
var OperationQueue = class
{
   constructor()
   {
      /** @type {number} Current status of the queue */
      this.status = OperationQueueStatus.INACTIVE;
      /** @type {number} Index of the currently executing operation, -1 if none */
      this.currentOperationIndex = -1;
      /** @type {boolean} Flag indicating if interruption has been requested */
      this.interruptionRequested = false;
      /** @type {Function|undefined} Callback function called after each operation step */
      this.stepCallback = undefined;
      /** @type {number} Total execution time of all operations */
      this.executionTime = 0;
      /** @type {ElapsedTime} Timer for tracking operation duration */
      this.elapsed = new ElapsedTime;
      /** @type {string|undefined} Event script code to be executed at operation events */
      this.eventScriptCode = undefined;

      /** @type {Object} The environment shared across operations */
      this.environment = {};

      /** @type {Array<{operation: OperationBlock, params: Object}>} List of operations with their parameters */
      this.operations = [];
   }

   /**
    * Requests interruption of the currently running queue. Bound as an arrow
    * function so it can be safely passed as a callback.
    */
   requestInterruption = () =>
   {
      this.interruptionRequested = true;
   };

   /**
    * Adds an operation to the queue. The operation is appended to the existing operations.
    *
    * @param {OperationBlock} operation The operation block to add
    * @param {Object} params Parameters object accessible at execution time via env.params
    * @returns {void}
    */
   addOperation( operation, params )
   {
      // queue the operation and the external params
      operation.__index__ = this.operations.length;
      this.operations.push(
      {
         operation: operation,
         params: params
      } );
   }

   /**
    * Adds an operation block created from a function. This is a convenience method that
    * wraps a function in an OperationBlock instance.
    *
    * @param {Function} operationBlock Function with (environment, requestInterruption) parameters
    * @param {Object} params Parameters object accessible at execution time via env.params
    * @return {OperationBlock} The newly created and added OperationBlock
    */
   addOperationBlock( operationBlock, params )
   {
      let operation = new OperationBlock;
      operation.run = function( env, requestInterruption )
      {
         operationBlock( env, requestInterruption );
      };
      this.addOperation( operation, params );
      return operation;
   }

   /**
    * Returns the operation at the given index in the queue.
    *
    * @param {number} i The index of the operation to retrieve
    * @return {OperationBlock|undefined} The operation if index is valid, undefined otherwise
    */
   operationAtIndex( i )
   {
      if ( i < 0 || i >= this.operations.length )
         return undefined;
      return this.operations[ i ].operation;
   }

   /**
    * Returns the currently active operation in the queue.
    *
    * @return {OperationBlock|undefined} The active operation, undefined if no operation is active
    */
   currentOperation()
   {
      return this.operationAtIndex( this.currentOperationIndex );
   }

   /**
    * Clears the queue by removing all operations and resetting the environment.
    * This effectively resets the queue to its initial state.
    *
    * @returns {void}
    */
   clear()
   {
      // clear the environment
      this.environment = {};
      this.operations = [];
   }

   /**
    * Executes the provided event script code by injecting the environment object.
    * The script is executed in a protected context to handle errors gracefully.
    *
    * @param {string} scriptCode JavaScript code to execute
    * @param {Object} env Environment object to inject into the script context
    * @return {boolean|Error} Returns true if execution succeeded, Error object if failed
    */
   executeEventScriptCode( scriptCode, env )
   {
      let code = "let success = false; try { if (!env.test) { " + scriptCode + " } success = true; } catch (e) { console.noteln(\"event script error: \", e); } success;";
      let success = false;
      try
      {
         engine.env = env
         success = eval( code );
         engine.env = undefined;
      }
      catch ( e )
      {
         console.warningln( "Pipeline event script failed: ", e );
         engine.env = undefined;
         return e;
      }
      return success;
   }

   /**
    * Installs an event script from a file. The script is validated before installation
    * by executing it in a test environment. Only successfully validated scripts are installed.
    *
    * @param {string} filePath Path to the JavaScript file containing the event script
    * @returns {boolean|undefined} true if installation succeeded, undefined if file doesn't exist or validation failed
    */
   installEventScript( filePath )
   {
      if ( !File.exists( filePath ) )
      {
         return undefined;
      }

      try
      {
         const scriptCode = File.readTextFile( filePath );
         const testEnvironment = {
            test: true
         };
         const success = this.executeEventScriptCode( scriptCode, testEnvironment );

         if ( success === true )
         {
            this.eventScriptCode = scriptCode;
            console.noteln( "Successfully installed the pipeline event script ", filePath );
         }
         else
         {
            this.eventScriptCode = undefined;
         }
         return success;
      }
      catch ( e )
      {
         console.warningln( "Failed to install event script: ", e );
         this.eventScriptCode = undefined;
         return undefined;
      }
   }

   /**
    * Uninstalls the currently installed event script.
    * After calling this method, no event scripts will be executed during operation processing.
    *
    * @returns {void}
    */
   uninstallEventScript()
   {
      this.eventScriptCode = undefined;
   }

   /**
    * Synchronously runs all operations in the queue. This method processes each operation
    * in sequence, handling initialization, execution, and cleanup phases. It supports
    * interruption and event triggering at various stages of execution.
    *
    * @param {Object} env Environment object to be shared across operations
    * @returns {void}
    */
   run( env )
   {
      // initialization
      this.executionTime = 0;
      this.elapsed.reset();
      this.environment = ( typeof env == "object" ) ? env
         :
         {};
      this.status = OperationQueueStatus.RUNNING;
      this.interruptionRequested = false;
      this.currentOperationIndex = -1;
      if ( typeof this.stepCallback == 'function' )
         this.stepCallback();

      // invoke the event script at the beginning of the execution
      this.triggerOperationWithEvent( undefined, "pipeline start" );

      // processing the queue
      for ( let i = 0; i < this.operations.length; i++ )
      {
         this.currentOperationIndex = i;
         this.executeTask( i );
         if ( this.interruptionRequested )
         {
            for ( let j = i + 1; j < this.operations.length; j++ )
               this.operations[ j ].operation.status = OperationBlockStatus.CANCELED;
            break;
         }
         CoreApplication.processEvents();
      }
      this.executionTime = this.elapsed.value;

      // clean up
      this.currentOperationIndex = -1;
      this.status = OperationQueueStatus.INACTIVE;

      // invoke the event script at the end of the execution
      this.triggerOperationWithEvent( undefined, "pipeline end" );

      if ( typeof this.stepCallback == 'function' )
         this.stepCallback();
   }

   /**
    * Triggers an operation-related event by executing the installed event script.
    * This method handles both generic pipeline events and operation-specific events.
    *
    * @param {Object|undefined} op Operation object for operation-specific events, undefined for generic events
    * @param {string} eventName Name of the event to trigger (e.g., "start", "done", "pipeline start", "pipeline end")
    * @returns {void}
    */
   triggerOperationWithEvent( op, eventName )
   {
      // operation is performed only if
      // - a pipeline event script is installed
      // - no operation is provided (generic event)
      // - an operation is given and the operation triggers an event
      if ( this.eventScriptCode != undefined && ( op == undefined || op.operation.triggersEventScript ) )
      {
         // get the data to be injected into the environment from the operation
         let env = {
            test: false,
            requestInterruption: this.requestInterruption
         };
         // if an operation is provided then inject the operation information
         if ( op )
         {
            if ( op.operation.envForScript )
            {
               let scriptEnv = op.operation.envForScript();
               let keys = Object.keys( scriptEnv );
               for ( let i = 0; i < keys.length; i++ )
                  env[ keys[ i ] ] = scriptEnv[ keys[ i ] ];
            }
            // operation details
            env.operationIndex = op.operation.__index__;
            env.operation = op.operation;
         }
         env.event = eventName;
         env.operationsCount = this.operations.length;
         this.executeEventScriptCode( this.eventScriptCode, env );
      }
   }

   /**
    * Handles the execution of a single task in the queue.
    * Tasks are only executed if they are in READY state. The method handles the complete
    * lifecycle of task execution including event triggering and status updates.
    *
    * @param {number} index The index of the task to execute in the operations array
    * @returns {void}
    */
   executeTask( index )
   {
      const operation = this.operations[ index ] && this.operations[ index ].operation;
      if ( !operation || operation.status !== OperationBlockStatus.READY )
      {
         return;
      }

      try
      {
         operation.status = OperationBlockStatus.RUNNING;

         if ( typeof this.stepCallback === 'function' )
         {
            this.stepCallback();
         }

         this.triggerOperationWithEvent( this.operations[ index ], "start" );

         // _perform() delegates to the operation's run() method, which returns
         // the final status (DONE, FAILED, or CANCELED). _perform() handles
         // all exceptions internally and sets operation.status accordingly,
         // so we must not overwrite it after the call returns.
         this.environment.params = this.operations[ index ].params;
         operation._perform( this.environment, this.requestInterruption );

         this.triggerOperationWithEvent( this.operations[ index ], "done" );

         if ( typeof this.stepCallback === 'function' )
         {
            this.stepCallback();
         }
      }
      catch ( e )
      {
         console.warningln( "Operation execution failed: ", e );
         operation.status = OperationBlockStatus.FAILED;
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-OperationQueue.js - Released 2026-05-10T11:05:00Z
