// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-TestChecker.js - Released 2026-05-10T11:05:00Z
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

var EVENT_PIPELINE_START = "pipeline start";
var EVENT_PIPELINE_END = "pipeline end";
var EVENT_START = "start";
var EVENT_END = "end";
var EVENT_DONE = "done";

// Operation status (must match OperationBlockStatus enum values)
var OPERATION_STATUS_READY = 0;
var OPERATION_STATUS_DONE = 2;

// Test runner messages
var MSG_TEST_FAILED = "TEST FAILED";
var MSG_TEST_EXECUTION_COMPLETED = "TEST EXECUTION COMPLETED";
var MSG_ENGINE_NO_TEST_STATUS = "Engine does not contain the test execution status object";
var MSG_ENGINE_WRONG_STRUCTURE = "Engine does not contain the list of operations array, wrong object structure";
var MSG_TRACKABLE_OPS_MISMATCH = "Number of trackable operations: ";
var MSG_PIPELINE_OP_NOT_DONE = "TEST FAILED: pipeline execution ended but operation #";
var MSG_PROGRESS = "PROGRESS: ";
var MSG_STEP_SUCCESS = "STEP #";
var MSG_STEP_FAILED = "STEP #";
var MSG_EXPECTED_FIELD = "expected field ";
var MSG_WITH_TEST_VALUE = " with test value of\n[";
var MSG_BUT_GOT = "]\nbut got\n[";
var MSG_END_EVENT = "end event: ";

var trackableOperations = engine.operationQueue.operations.filter( o => o && o.operation && !!o.operation.triggersEventScript );
var trackableOperationsCount = trackableOperations.length;
var trackableIndex = 0;
var terminate = false;

console.noteln( "[TestChecker] event: " + env.event + " | trackableOps: " + trackableOperationsCount );

if ( env.event == EVENT_START || env.event == EVENT_END )
{
   // find the trackable operation index
   for ( let i = 0; i < trackableOperationsCount; i++ )
      if ( trackableOperations[ i ].operation.__index__ == env.operationIndex )
      {
         trackableIndex = i;
         break;
      }
}

// -------------------------
// ---  PIPELINE STARTED
// -------------------------

if ( env.event == EVENT_PIPELINE_START && !engine.recordTest )
{
   if ( engine.executionStatus == undefined )
   {
      console.warningln( "[TestChecker] FAIL: engine.executionStatus is undefined" );
      cout( "\n" + MSG_ENGINE_NO_TEST_STATUS );
      cout( "\n" + MSG_TEST_FAILED );
      engine.operationQueue.requestInterruption();
      engine.operationQueue.__interruptedFromTestCheckedScript__ = true;
      terminate = true;
   }
   else if ( engine.executionStatus.ops == undefined )
   {
      console.warningln( "[TestChecker] FAIL: engine.executionStatus.ops is undefined" );
      cout( "\n" + MSG_ENGINE_WRONG_STRUCTURE );
      cout( "\n" + MSG_TEST_FAILED );
      engine.operationQueue.requestInterruption();
      engine.operationQueue.__interruptedFromTestCheckedScript__ = true;
      terminate = true;
   }
   else
   {
      let expectedTrackableOperationsCount = engine.executionStatus.ops
         .filter( o => o && o.operation && !!o.operation.triggersEventScript ).length;
      console.noteln( "[TestChecker] pipeline start: current trackable=" + trackableOperationsCount + " expected=" + expectedTrackableOperationsCount );
      if ( trackableOperationsCount != expectedTrackableOperationsCount )
      {
         console.warningln( "[TestChecker] FAIL: trackable ops mismatch: current=" + trackableOperationsCount + " expected=" + expectedTrackableOperationsCount );
         cout( "\n" + MSG_TRACKABLE_OPS_MISMATCH + trackableOperationsCount + ", but got " + expectedTrackableOperationsCount );
         cout( "\n" + MSG_TEST_FAILED );
         engine.operationQueue.requestInterruption();
         engine.operationQueue.__interruptedFromTestCheckedScript__ = true;
         terminate = true;
      }
   }
}

// -------------------------
// ---  PIPELINE TERMINATED
// -------------------------

if ( !terminate && env.event == EVENT_PIPELINE_END )
{
   if ( !engine.recordTest )
   {
      // all steps must be successfully executed
      let success = true;
      let i = 0;
      for ( ; success && i < engine.operationQueue.operations.length; i++ )
      {
         let status = engine.operationQueue.operations[ i ].operation.status;
         success = status == undefined || status == OPERATION_STATUS_DONE || status == OPERATION_STATUS_READY;
      }

      if ( !success )
      {
         cout( "\n" + MSG_PIPELINE_OP_NOT_DONE + i + " is not done" );
         cout( "\n" + MSG_TEST_FAILED );
      }
   }

   cout( "\n" + MSG_TEST_EXECUTION_COMPLETED );
}

// -------------------------
// ---  STEP START
// -------------------------

if ( !terminate && env.event == EVENT_START )
{
   // provide information on the current progress
   cout( "\n" + MSG_PROGRESS + ( trackableIndex + 1 ) + " / " + trackableOperationsCount );
}

// -------------------------
// ---  STEP DONE
// -------------------------

// we check when an operation is done
if ( !terminate && env.event == EVENT_DONE && !engine.recordTest )
{
   // check against result and current execution
   let testOperation = engine.executionStatus.ops[ env.operationIndex ];
   let operation = env.operation;

   console.noteln( "[TestChecker] EVENT_DONE: operationIndex=" + env.operationIndex + " testOperation=" + ( testOperation ? "exists" : "null/undefined" ) );

   cout( "\nenv.operationIndex: " + env.operationIndex );
   cout( "\ntestOperation: " + testOperation );

   // the index, result and notes must be the same
   let success = true;
   let keys = Object.keys( testOperation );
   for ( let i = 0; success && i < keys.length; i++ )
   {
      let key = keys[ i ];
      let testValue = testOperation[ key ];
      if ( typeof( testValue ) == "string" && testValue != operation[ key ] )
      {
         let msg = MSG_EXPECTED_FIELD + key + MSG_WITH_TEST_VALUE + testValue + MSG_BUT_GOT + operation[ key ] + "]";
         console.warningln( "[TestChecker] STEP FAILED: " + msg );
         cout( "\n" + MSG_STEP_FAILED + ( trackableIndex + 1 ) + " failed: " + msg );
         engine.operationQueue.requestInterruption();
         engine.operationQueue.__interruptedFromTestCheckedScript__ = true;
         success = false;
      }
   }
   if ( success )
   {
      console.noteln( "[TestChecker] STEP #" + ( trackableIndex + 1 ) + " success" );
      cout( "\n" + MSG_STEP_SUCCESS + ( trackableIndex + 1 ) + " success" );
   }
}

cout( "\n" + MSG_END_EVENT + env.event );

if ( typeof cflush === "function" )
   cflush();
System.sleep( 1 );

// ----------------------------------------------------------------------------
// EOF BPP-TestChecker.js - Released 2026-05-10T11:05:00Z
