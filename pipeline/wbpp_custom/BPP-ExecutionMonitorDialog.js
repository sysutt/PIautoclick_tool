// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ExecutionMonitorDialog.js - Released 2026-05-10T11:05:00Z
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
 * Dialog for monitoring pipeline execution progress and displaying execution
 * reports. Shows a tree of operations with status icons, elapsed time, and
 * notes. Can operate in live monitoring mode (with cancel button) or as a
 * post-execution report (with done button).
 *
 * @param {boolean} asReport - Whether the dialog is used as a report or not
 * @param {Function} executionCancelRequestCallback - Callback to handle execution cancellation
 * @param {Array} operations - Array of operations to display in the dialog
 * @param {Function} onTerminationRequest - Callback to handle termination request
 */
var ExecutionMonitorDialog = class extends Dialog
{
   constructor( asReport, executionCancelRequestCallback, operations, onTerminationRequest )
   {
      super();

      this.columnSizesAdjusted = false
      this.cancelRequested = false;

      // Store constructor params for use in onReturn class field
      this._cancelCallback = executionCancelRequestCallback;
      this._onTerminationRequest = onTerminationRequest;

      this.infoTreeBox = new TreeBox( this );
      this.infoTreeBox.rootDecoration = false;
      this.infoTreeBox.headerVisible = true;
      this.infoTreeBox.headerSorting = false;
      this.infoTreeBox.alternateRowColor = true;
      this.infoTreeBox.numberOfColumns = 5;

      this.infoTreeBox.setHeaderText( 0, "Operation" );
      this.infoTreeBox.setHeaderText( 1, "Group involved" );
      this.infoTreeBox.setHeaderText( 2, "Elapsed" );
      this.infoTreeBox.setHeaderText( 3, "Status" );
      this.infoTreeBox.setHeaderText( 4, "Note" );

      if ( this._cancelCallback )
      {
         this.cancelButton = new PushButton( this );
         this.cancelButton.defaultButton = true;
         this.cancelButton.text = "Cancel";
         this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
         this.cancelButton.onClick = () =>
         {
            if ( this.cancelRequested )
            {
               this.ok();
            }
            else
            {
               if ( this._onTerminationRequest )
                  this._onTerminationRequest();
               this._cancelCallback();
               this.cancelRequested = true;
            }
         };
      }

      if ( asReport )
      {
         this.okButton = new PushButton( this );
         this.okButton.defaultButton = true;
         this.okButton.text = "DONE";
         this.okButton.onClick = () =>
         {
            this.ok();
         };
      }

      this.noteLabel = new Label( this );
      let f = this.noteLabel.font;
      f.bold = true;
      this.noteLabel.font = f;
      this.noteLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;

      this.buttonsSizer = new HorizontalSizer;
      this.buttonsSizer.add( this.noteLabel );
      this.buttonsSizer.addStretch();
      if ( this._cancelCallback )
      {
         this.buttonsSizer.addSpacing( 8 );
         this.buttonsSizer.add( this.cancelButton );
      }
      if ( asReport )
      {
         this.buttonsSizer.addSpacing( 8 );
         this.buttonsSizer.add( this.okButton );
      }

      this.sizer = new VerticalSizer;
      this.sizer.margin = 8;
      this.sizer.add( this.infoTreeBox );
      this.sizer.addSpacing( 8 );
      this.sizer.add( this.buttonsSizer );

      this.ensureLayoutUpdated();
      this.adjustToContents();
      this.setMinSize();

      this.windowTitle = ( engine.fastMode ? "FBPP" : "WBPP" ) + " Execution Monitor";

      // init with operations
      if ( operations )
         this.updateWithOperations( operations );

      this.restoreDialogFrame();
   }

   /** @type {Object} SVG icon paths for operation status indicators. */
   static ICONS = {
      ready: ":/bullets/bullet-circle-void.svg",
      done: ":/bullets/bullet-check-green.svg",
      doneWithWarnings: ":/bullets/bullet-circle-purple.svg",
      running: ":/bullets/bullet-triangle-blue.svg",
      failed: ":/bullets/bullet-circle-red.svg",
      cancel: ":/bullets/bullet-cross.svg"
   };

   /**
    * Rebuilds the entire operations tree from scratch. Updates status icons,
    * elapsed time, text colors, and column widths.
    *
    * @param {Array<OperationBlock>} operations - Operations to display
    */
   updateWithOperations = ( operations ) =>
   {
      // ensure we're not invoking this function after the interruption of a timer
      if ( this.updatingWithOperations )
         return;
      this.updatingWithOperations = true;

      let activeNode;
      this.infoTreeBox.clear();
      for ( let i = 0; i < operations.length; ++i )
      {
         let node = new TreeBoxNode;
         // operation index
         node.setText( 0, operations[ i ].name );
         // group info
         node.setText( 1, operations[ i ].groupDescription );
         // elapsed
         if ( operations[ i ].status == OperationBlockStatus.READY )
            node.setText( 2, "" );
         else if ( operations[ i ].status == OperationBlockStatus.RUNNING )
            node.setText( 2, WBPPUtils.elapsedTimeToString( operations[ i ].elapsed.value ) );
         else
            node.setText( 2, WBPPUtils.elapsedTimeToString( operations[ i ].executionTime ) );
         // status
         switch ( operations[ i ].status )
         {
            case OperationBlockStatus.READY:
               operations[ i ].updateGroupDescription();
               node.setIcon( 3, ExecutionMonitorDialog.ICONS.ready );
               break;
            case OperationBlockStatus.RUNNING:
               activeNode = node;
               if ( this.cancelRequested )
                  node.setText( 3, "canceling..." );
               else
                  node.setText( 3, "running" );
               node.setIcon( 3, ExecutionMonitorDialog.ICONS.running );
               break;
            case OperationBlockStatus.DONE:
               node.setText( 3, "success" );
               if ( operations[ i ].hasWarnings )
                  node.setIcon( 3, ExecutionMonitorDialog.ICONS.doneWithWarnings );
               else
                  node.setIcon( 3, ExecutionMonitorDialog.ICONS.done );
               break;
            case OperationBlockStatus.FAILED:
               node.setText( 3, "failed" );
               node.setIcon( 3, ExecutionMonitorDialog.ICONS.failed );
               break;
            case OperationBlockStatus.CANCELED:
               node.setText( 3, "canceled" );
               node.setIcon( 3, ExecutionMonitorDialog.ICONS.cancel );
               break;
         }
         // notes
         if ( operations[ i ].status != OperationBlockStatus.RUNNING )
         {
            node.setText( 4, operations[ i ].statusMessage );
         }

         this.infoTreeBox.add( node );
      }

      if ( activeNode )
      {
         activeNode.setTextColor( 0, 0x0000BB );
         activeNode.setTextColor( 1, 0x0000BB );
         activeNode.setTextColor( 2, 0x0000BB );
         if ( this.cancelRequested )
            activeNode.setTextColor( 3, 0xBB0000 );
         else
            activeNode.setTextColor( 3, 0x0000BB );
      }

      if ( !this.columnSizesAdjusted )
      {
         this.columnSizesAdjusted = true;
         this.infoTreeBox.adjustColumnWidthToContents( 0 );
         this.infoTreeBox.adjustColumnWidthToContents( 1 );

      }
      // elapsed always get adjusted
      this.infoTreeBox.adjustColumnWidthToContents( 2 );
      // status always get adjusted
      this.infoTreeBox.adjustColumnWidthToContents( 3 );


      // scroll follows the current active node in automation mode
      if ( activeNode )
         this.infoTreeBox.setNodeIntoViewport( activeNode );

      this.updatingWithOperations = false;
   };

   /**
    * Lightweight update that only refreshes the elapsed time and cancel status
    * of the currently running operation, without rebuilding the full tree.
    *
    * @param {Array<OperationBlock>} operations - Operations to check
    */
   updateRunningOperation = ( operations ) =>
   {
      if ( this.updatingWithOperations )
         return;
      this.updatingWithOperations = true;

      for ( let i = 0; i < operations.length; ++i )
         if ( operations[ i ].status == OperationBlockStatus.RUNNING )
            if ( i < this.infoTreeBox.numberOfChildren )
            {
               let node = this.infoTreeBox.child( i );
               node.setText( 2, WBPPUtils.elapsedTimeToString( operations[ i ].elapsed.value ) );
               if ( this.cancelRequested )
               {
                  node.setText( 3, "canceling..." );
                  node.setTextColor( 3, 0xBB0000 );
                  this.infoTreeBox.adjustColumnWidthToContents( 3 );
               }
               break;
            }
      this.updatingWithOperations = false;
   };

   /**
    * Computes and applies an initial dialog frame size based on the tree
    * content. Only runs once; subsequent calls are no-ops.
    */
   adjustDialogFrame = () =>
   {
      // frame has already been adjusted once
      if ( ExecutionMonitorDialog.prototype.__frame__ )
         return;

      // get the rect of the last node
      let width = 680;
      let height = 300;
      if ( this.infoTreeBox.numberOfChildren > 0 )
      {
         let lastNode = this.infoTreeBox.child( this.infoTreeBox.numberOfChildren - 1 );
         let frame = this.infoTreeBox.nodeRect( lastNode );
         width = frame.x1;
         height = frame.y1;
      }

      width = Math.min( this.availableScreenRect.width - 100, width + 120 );
      height = Math.min( this.availableScreenRect.height - 200, height + 200 );

      let x = ( this.availableScreenRect.width - width ) / 2;
      let y = ( this.availableScreenRect.height - height ) / 2;
      this.position = new Point( x, y );
      this.width = width;
      this.height = height;

      this.storeDialogFrame();
   };

   /**
    * Persists the current dialog position and size to the prototype for
    * reuse across dialog instances.
    */
   storeDialogFrame = () =>
   {
      let frame = {
         position: new Point( this.position ),
         width: this.width,
         height: this.height
      };
      ExecutionMonitorDialog.prototype.__frame__ = frame;
   };

   /**
    * Restores a previously stored dialog position and size.
    */
   restoreDialogFrame = () =>
   {
      let frame = ExecutionMonitorDialog.prototype.__frame__;
      if ( frame )
      {
         this.position = new Point( frame.position );
         this.width = frame.width;
         this.height = frame.height;
      }
   };

   /**
    * Dialog return handler. Stores the frame and, if dismissed without
    * pressing Cancel, triggers termination and cancel callbacks.
    *
    * @param {number} retVal - Dialog return value (0 = dismissed)
    */
}

ExecutionMonitorDialog.prototype.onReturn = function( retVal )
{
   this.storeDialogFrame();
   if ( retVal == 0 && this._cancelCallback )
   {
      /* dialog dismissed without pressing CANCEL button */
      if ( this._onTerminationRequest )
         this._onTerminationRequest();
      this._cancelCallback();
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-ExecutionMonitorDialog.js - Released 2026-05-10T11:05:00Z
