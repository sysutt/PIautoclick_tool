// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-GUI.js - Released 2026-05-10T11:05:00Z
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
 * Graphical user interface
 */

#include "BPP-Graph.js"

// ----------------------------------------------------------------------------

/**
 * Base TreeBox Control.
 *
 * @param {*} parent
 */
var StyledTreeBox = class extends TreeBox
{
   constructor( parent )
   {
      super( parent );

      this.alternateRowColor = true;
      // Add a bit of horizontal space between columns for improved readability.
      this.styleSheet = "QTreeView::item { padding-left: 0.25em; padding-right: 0.25em; }";
   }
}

// ----------------------------------------------------------------------------

/**
 * Describes the properties of a treeBox like header names and column widths for
 * a given image type.
 *
 * @param {ImageType} imageType
 */
function GroupTreeBoxDescriptor( imageType )
{
   this.imageType = imageType;

   /**
    * Returns the headers for be shown for the given mode
    *
    * @param {WBPPGroupingMode} mode
    * @returns
    */
   this.headers = ( mode ) =>
   {
      let headers = [];
      switch ( mode )
      {
         case BPP.GroupingMode.PRE:
            switch ( this.imageType )
            {
               case ImageType.Bias:
                  headers = [ "#", "BIAS", "Bin", "Overscan\nInfo" ];
                  break;
               case ImageType.Dark:
                  headers = [ "#", "DARK", "Bin", "Exposure", "Overscan\nInfo" ];
                  break;
               case ImageType.Flat:
                  headers = [ "#", "FLAT", "Bin", "Exposure", "Filter",
                     "STATUS", "Bias", "Dark", "Optimize\nDark",
                     "CFA\nImages", "Overscan\nInfo"
                  ];
                  break;
               case ImageType.Light:
                  headers = engine.fastMode ? [ "#", "LIGHT", "Bin", "Exposure", "Filter", "STATUS",
                     "Bias", "Dark", "Flat", "Optimize\nDark", "Cosmetic\nCorrection", "CFA\nImages"
                  ] : [ "#", "LIGHT", "Bin", "Exposure", "Filter", "STATUS",
                     "Bias", "Dark", "Flat", "Optimize\nDark",
                     "Output\nPedestal (DN)", "Cosmetic\nCorrection", "CFA\nImages"
                  ];
                  break;
            }
            break;

         case BPP.GroupingMode.POST:
            switch ( this.imageType )
            {
               case ImageType.Light:
                  headers = [ "LIGHT", "Bin", "Exposures", "Filter", "Color Space",
                     "Integration Time", "Fast\nIntegration", "Drizzle", "Status"
                  ];
            }
            break;
      }

      return headers;
   };
}

// ----------------------------------------------------------------------------
/**
 * Base control for grouping controls in an optionally collapsable panel.
 */
var ParametersControl = class extends Control
{
   constructor( title, parent, expand, deactivatable, collapsable, withReset, withSettings )
   {
      super( parent );

      if ( parent )
      {
         if ( !parent.parameterControls )
            parent.parameterControls = new Array;
         parent.parameterControls.push( this );
         this.parent = parent;
      }

      if ( expand )
      {
         this.expand = expand;
         this.makeHidden();
      }
      else
         this.expand = false;

      // start always non collapsed
      this.collapsed = false;

      // Force this generic control to inherit the dialog font.
      // In V8, this.dialog may not resolve during construction; walk parent chain.
      let ownerDialog = this.dialog;
      if ( !ownerDialog )
      {
         let p = parent;
         while ( p && !( p instanceof Dialog ) )
            p = p.parent;
         if ( p )
            ownerDialog = p;
      }
      if ( ownerDialog )
         this.font = ownerDialog.font;

      // title bar construction
      if ( deactivatable == true )
      {
         this.activatableCheckbox = new CheckBox( this );
         this.activatableCheckbox.setScaledFixedSize( 20, 20 );
         this.activatableCheckbox.checked = true;
         this.activatableCheckbox.onCheck = ( value ) =>
         {
            this.contents.enabled = value;
            // invoke the callback if registered
            if ( this.onActivateStatusChanged )
               this.onActivateStatusChanged( value );
         };
      }

      this.titleLabel = new Label( this );
      this.titleLabel.text = title ? title : "";
      this.titleLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;

      if ( withReset )
      {
         this.resetButton = new ToolButton( this );
         this.resetButton.icon = this.scaledResource( ":/icons/reload.png" );
         this.resetButton.setScaledFixedSize( 22, 22 );
         this.resetButton.toolTip = "<p>Reset panel parameters to default values</p>";
         this.resetButton.onClick = function()
         {
            if ( this.parent.parent.reset )
               if ( typeof this.parent.parent.reset == "function" )
                  this.parent.parent.reset();
         };
      }
      else
         this.resetButton = null;

      if ( withSettings )
      {
         this.settingsButton = new ToolButton( this );
         this.settingsButton.icon = this.scaledResource( ":/icons/process.png" );
         this.settingsButton.setScaledFixedSize( 22, 22 );
         this.settingsButton.toolTip = "<p>Open panel settings</p>";
         this.settingsButton.onClick = function()
         {
            if ( this.parent.parent.settings )
               if ( typeof this.parent.parent.settings == "function" )
                  this.parent.parent.settings();
         };
      }
      else
         this.settingsButton = null;

      if ( this.expand )
      {
         this.closeButton = new ToolButton( this );
         this.closeButton.icon = this.scaledResource( ":/icons/close.png" );
         this.closeButton.setScaledFixedSize( 22, 22 );
         this.closeButton.toolTip = "Back";
         this.closeButton.onClick = () =>
         {
            this.makeHidden();
         };
      }
      else
         this.closeButton = null;

      // prepare the title bar control — use platform SectionBar styling
      this.titleBar = new Control( this );
      this.titleBar.objectId = "IWSectionBar";
      this.titleBar.sizer = new HorizontalSizer;
      this.titleBar.sizer.margin = 2;

      // add the activate checkbox if needed
      if ( this.activatableCheckbox )
      {
         this.titleBar.sizer.addSpacing( 8 );
         this.titleBar.sizer.add( this.activatableCheckbox );
      }

      // add the title checkbox if needed
      this.titleBar.sizer.add( this.titleLabel );
      this.titleBar.sizer.addStretch();

      // add the reset button if requested
      if ( withReset )
      {
         this.titleBar.sizer.add( this.resetButton );
         this.titleBar.sizer.addSpacing( 4 );
      }

      // add the settings button if requested
      if ( withSettings )
      {
         this.titleBar.sizer.add( this.settingsButton );
         this.titleBar.sizer.addSpacing( 4 );
      }

      // add the close button if needed
      if ( this.expand )
      {
         this.titleBar.sizer.add( this.closeButton );
         this.titleBar.sizer.addSpacing( 4 );
      }

      // add the collapsable button (visible only if collapsable is enabled)
      this.collapseButton = new ToolButton( this );
      this.collapseButton.visible = ( collapsable != undefined ) ? collapsable : false;
      this.collapseButton.icon = this.scaledResource( ":/auto-hide/expand.png" );
      this.collapseButton.setScaledFixedSize( 20, 20 );
      this.collapseButton.toolTip = "Group's expand/collapse toggle button.";
      this.collapseButton.onClick = () =>
      {
         this.collapse( !this.collapsed );
         if ( typeof this.onCollapse == "function" )
            this.onCollapse( this.collapsed );
      };
      this.titleBar.sizer.add( this.collapseButton );
      this.titleBar.sizer.addSpacing( 4 );

      // prepare the contents container
      this.contents = new Control( this );
      this.contents.objectId = "IWSectionBarControl";

      this.contents.sizer = new VerticalSizer;
      this.contents.sizer.margin = 6;
      this.contents.sizer.spacing = 6;
      this.contents.sizer.addSpacing( 8 );

      this.sizer = new VerticalSizer;
      this.sizer.add( this.titleBar );
      this.sizer.add( this.contents );
   }

   makeVisible()
   {
      this.visible = true;
      if ( this.expand )
         for ( let i = 0; i < this.parent.parameterControls.length; ++i )
         {
            let sibling = this.parent.parameterControls[ i ];
            if ( sibling !== this )
               sibling.hide();
         }
   }

   makeHidden()
   {
      this.visible = false;
      if ( this.expand )
         for ( let i = 0; i < this.parent.parameterControls.length; ++i )
         {
            let sibling = this.parent.parameterControls[ i ];
            if ( !sibling.expand && sibling !== this && !( sibling.__alwaysHidden__ || false ) )
               sibling.show();
         }
   }

   setActivatableCheckboxTooltip( tooltip )
   {
      if ( this.activatableCheckbox != undefined )
         this.activatableCheckbox.toolTip = tooltip;
   }

   add( control )
   {
      this.contents.sizer.add( control );
   }

   activate()
   {
      if ( this.activatableCheckbox )
      {
         this.activatableCheckbox.checked = true
         this.titleLabel.enabled = true;
      };
      this.contents.enabled = true;
   }

   deactivate()
   {
      if ( this.activatableCheckbox )
      {
         this.activatableCheckbox.checked = false
         this.titleLabel.enabled = false;
      };
      this.contents.enabled = false;
   }

   makeCollapsable( collapsable )
   {
      collapsable = collapsable != undefined ? collapsable : true;
      // expand if control is no more collapsable
      this.collapsable = collapsable;
      if ( !collapsable )
         this.collapse( false );
      // remove the collapsable feature
      this.collapseButton.visible = collapsable;
   }

   collapse( collapsed )
   {
      // collapse has effect only if the control is collapsable
      this.collapsed = this.collapsable && collapsed;
      this.contents.visible = !this.collapsed;
      // titleBar styling is handled by platform via objectId = "IWSectionBar"
   }
};

// ----------------------------------------------------------------------------
// GLOBAL OPTIONS GROUPS
// ----------------------------------------------------------------------------

var PresetsControl = class extends ParametersControl
{
   constructor( title, parent )
   {
      super( title, parent );

      let label = new Label( this );
      label.useRichText = true;
      label.wordWrapping = true;
      label.text = "<p>Configure WBPP for maximum speed or quality.</p>";

      let selectButton = new PushButton( this );
      selectButton.text = "SELECT";
      selectButton.onClick = function()
      {
         let presetsDialog = new PresetsDialog;
         let preset = presetsDialog.execute();
         if ( preset > 0 )
         {
            engine.parametersManager.applyPreset( preset );
            this.dialog.updateControls();
         }
      }

      this.add( label );
      this.add( selectButton );
   }
}

// ----------------------------------------------------------------------------

/**
 * This control allows to add/edit/remove a list of keywords and provide
 * an event-handler "onKeywordsUpdated" that is triggered when the list of
 * keywords changes.
 * By default, keyboard input is sanitized and capitalized, only alphanumeric
 * characters are allowed.
 *
 * @param {*} title
 * @param {*} parent
 */
var KeywordsEditor = class extends ParametersControl
{
   constructor( title, parent )
   {
      super( title, parent, false /* expandable */ , true /* deactivatable */ );

      // Internal state
      this.keywordSelected = false;

      // Keyword input
      this.keywordEdit = new Edit( this );
      this.keywordEdit.setScaledFixedHeight( 20 );

      this.keywordEdit.onTextUpdated = ( newText ) =>
      {
         let caretPosition = this.keywordEdit.caretPosition;
         this.keywordEdit.text = newText.replace( /[^a-z0-9-]/gmi, '' ).toUpperCase();
         this.keywordEdit.caretPosition = caretPosition + ( ( this.keywordEdit.text.length == newText.length ) ? 0 : -1 );
      };

      this.keywordEdit.onLoseFocus = () =>
      {
         this.keywordEdit.text = "";
         this.keywordSelected = false;
         this.updateToolButtons();
         this.selectionWasUpdated = false;
         this.refreshTreeBox();
      };

      // confirm button
      this.confirmButton = new ToolButton( this );
      this.confirmButton.setScaledFixedSize( 20, 20 );
      this.confirmButton.toolTip = "<p>By adding or updating a keyword, all the frame files will be"
         + "reprocessed and regrouped accordingly. Any setting that has been manually changed will be "
         + "set back to its default value.</p>";

      this.confirmButton.onClick = () =>
      {
         if ( this.keywordSelected )
            this.replaceCurrentKeyword(); // modify the selected keyword
         else
            this.addNewKeyword(); // add the typed keyword
      };

      // keyword list
      this.keywordsTreeBox = new TreeBox( this );
      this.keywordsTreeBox.alternateRowColor = true;
      this.keywordsTreeBox.multipleSelection = false;
      this.keywordsTreeBox.indentSize = 0;
      this.keywordsTreeBox.setScaledFixedHeight( 80 );

      // headers
      this.keywordsTreeBox.headerVisible = true;
      this.keywordsTreeBox.headerSorting = false;
      this.keywordsTreeBox.numberOfColumns = 3;
      this.keywordsTreeBox.setHeaderText( 0, "Keyword" );
      this.keywordsTreeBox.setHeaderText( 1, "Pre" );
      this.keywordsTreeBox.setHeaderText( 2, "Post" );
      this.keywordsTreeBox.setHeaderAlignment( 0, TextAlignment.Center );
      this.keywordsTreeBox.setHeaderAlignment( 1, TextAlignment.Center );
      this.keywordsTreeBox.setHeaderAlignment( 2, TextAlignment.Center );

      this.selectionWasUpdated = false;

      this.keywordsTreeBox.onNodeSelectionUpdated = ( programmatically ) =>
      {
         if ( !programmatically )
            this.selectionWasUpdated = true;
         if ( this.keywordsTreeBox.currentNode )
         {
            this.keywordSelected = true;
            this.keywordEdit.text = this.keywordsTreeBox.currentNode.text( 0 );
            this.updateToolButtons();
         }
      };

      this.keywordsTreeBox.onNodeClicked = () =>
      {
         if ( !this.selectionWasUpdated )
         {
            this.keywordEdit.text = "";
            this.keywordsTreeBox.currentNode.selected = false;
            this.keywordSelected = false;
            this.updateToolButtons();
         }
         this.selectionWasUpdated = false;
      };

      // keyword sort buttons
      this.moveUp = new ToolButton( this );
      this.moveUp.setScaledFixedSize( 20, 20 );
      this.moveUp.icon = this.scaledResource( ":/arrows/arrow-up.png" );
      this.moveUp.onClick = () => this.moveSelectedKeyword( true /* up */ );
      this.moveDown = new ToolButton( this );
      this.moveDown.setScaledFixedSize( 20, 20 );
      this.moveDown.icon = this.scaledResource( ":/arrows/arrow-down.png" );
      this.moveDown.onClick = () => this.moveSelectedKeyword( false /* up */ );

      // pre/post process switches
      this.switchWorkingMode = new ToolButton( this );
      this.switchWorkingMode.setScaledFixedSize( 20, 20 );
      this.switchWorkingMode.icon = this.scaledResource( ":/icons/processes.png" );
      this.switchWorkingMode.onClick = () =>
      {
         this.switchKeyword();
      };

      // cancel button
      this.cancelButton = new ToolButton( this );
      this.cancelButton.setScaledFixedSize( 20, 20 );
      this.cancelButton.toolTip = "<p>By removing a keyword, all the frame files will be"
         + "reprocessed and regrouped accordingly. Any setting that has been manually changed will be "
         + "set back to its default value.</p>";
      this.cancelButton.onClick = () => this.removeSelectedKeyword();
      this.cancelButton.icon = this.scaledResource( ":/toolbar/image-purge.png" );

      this.buttonsSizer = new VerticalSizer;
      this.buttonsSizer.spacing = 4;
      this.buttonsSizer.add( this.moveUp );
      this.buttonsSizer.add( this.moveDown );
      this.buttonsSizer.add( this.switchWorkingMode );
      this.buttonsSizer.add( this.cancelButton );
      this.buttonsSizer.addStretch();

      this.treeBoxAndButtonsSizer = new HorizontalSizer;
      this.treeBoxAndButtonsSizer.spacing = 4;
      this.treeBoxAndButtonsSizer.add( this.keywordsTreeBox );
      this.treeBoxAndButtonsSizer.add( this.buttonsSizer )

      // layout
      this.editRowSizer = new HorizontalSizer;
      this.editRowSizer.spacing = 4;
      this.editRowSizer.add( this.keywordEdit );
      this.editRowSizer.add( this.confirmButton );

      this.add( this.editRowSizer );
      this.add( this.treeBoxAndButtonsSizer );

      // AUX

      this.onActivateStatusChanged = ( active ) =>
      {
         engine.groupingKeywordsEnabled = active;
         this.onKeywordsUpdated();
      };

      this.updateContent();
   }

   refreshTreeBox()
   {
      this.keywordsTreeBox.clear();
      engine.keywords.list.forEach( keyword =>
      {
         let nodeTree = new TreeBoxNode( this.keywordsTreeBox );
         nodeTree.setText( 0, keyword.name );
         if ( keyword.mode & BPP.GroupingMode.PRE )
         {
            nodeTree.setIcon( 1, this.scaledResource( ":/browser/enabled.png" ) );
         }
         else
         {
            nodeTree.setIcon( 1, this.scaledResource( "" ) );
         }

         if ( keyword.mode & BPP.GroupingMode.POST )
         {
            nodeTree.setIcon( 2, this.scaledResource( ":/browser/enabled.png" ) );
         }
         else
         {
            nodeTree.setIcon( 2, this.scaledResource( "" ) );
         }
      } );
      this.keywordsTreeBox.adjustColumnWidthToContents( 0 );
      this.keywordsTreeBox.adjustColumnWidthToContents( 1 );
      this.keywordsTreeBox.adjustColumnWidthToContents( 2 );
   }

   updateToolButtons()
   {
      this.moveDown.enabled = this.keywordSelected;
      this.moveUp.enabled = this.keywordSelected;
      this.switchWorkingMode.enabled = this.keywordSelected;
      this.cancelButton.enabled = this.keywordSelected;

      if ( !this.keywordSelected )
         this.confirmButton.icon = this.scaledResource( ":/icons/add.png" );
      else
         this.confirmButton.icon = this.scaledResource( ":/script-editor/modified-document.png" );
   }

   addNewKeyword()
   {
      if ( this.keywordEdit.text.length == 0 )
      {
         // must type the keyword before adding it
         ( new MessageBox(
            "No keyword specified. Type your keyword and then click the add button.",
            "ERROR",
            StdIcon.Warning,
            StdButton.Ok
         ) ).execute();
         return;
      }

      // add the keyword
      let errorStr = engine.keywords.add( this.keywordEdit.text );
      if ( errorStr )
      {
         ( new MessageBox(
            errorStr,
            "ERROR",
            StdIcon.Warning,
            StdButton.Ok
         ) ).execute();
         return;
      }
      // success
      this.keywordEdit.text = "";
      this.refreshTreeBox();
      this.updateToolButtons();

      // event handler management
      if ( this.onKeywordsUpdated )
         this.onKeywordsUpdated();
   }

   replaceCurrentKeyword()
   {
      let oldKeyword = this.keywordsTreeBox.currentNode.text( 0 );
      if ( this.keywordEdit.text.length == 0 )
      {
         ( new MessageBox(
            "New keyword cannot be empty.",
            "ERROR",
            StdIcon.Warning,
            StdButton.Ok
         ) ).execute();
         return;
      }

      engine.keywords.replace( oldKeyword, this.keywordEdit.text );

      // done
      this.keywordSelected = false;
      this.keywordEdit.text = "";
      this.refreshTreeBox();
      this.updateToolButtons();

      // event handler management
      if ( this.onKeywordsUpdated )
         this.onKeywordsUpdated();
   }

   moveSelectedKeyword( up )
   {
      let name = this.keywordsTreeBox.currentNode.text( 0 );

      engine.keywords.move( name, up );
      this.refreshTreeBox();
      if ( this.onKeywordsUpdated )
         this.onKeywordsUpdated();
      this.selectKeyword( name );
   }

   switchKeyword()
   {
      if ( !this.keywordsTreeBox.currentNode )
         return;
      let name = this.keywordsTreeBox.currentNode.text( 0 );
      engine.keywords.switchMode( name )
      this.refreshTreeBox();
      if ( this.onKeywordsUpdated )
         this.onKeywordsUpdated();
      this.selectKeyword( name );
   }

   removeSelectedKeyword()
   {
      let keyword = this.keywordsTreeBox.currentNode.text( 0 );
      if ( keyword )
      {
         engine.keywords.remove( keyword );
         this.keywordSelected = false;
         this.keywordEdit.text = "";
         this.refreshTreeBox();
         this.updateToolButtons();
      }

      // event handler management
      if ( this.onKeywordsUpdated )
         this.onKeywordsUpdated();
   }

   selectKeyword( name )
   {
      for ( let i = 0; i < this.keywordsTreeBox.numberOfChildren; ++i )
      {
         let node = this.keywordsTreeBox.child( i );
         if ( node.text( 0 ) == name )
         {
            this.keywordsTreeBox.currentNode = this.keywordsTreeBox.child( i )
            break;
         }
      }
      this.keywordsTreeBox.onNodeSelectionUpdated( true /* programmatically */ )
   }

   reset()
   {
      this.keywordSelected = false;
      this.keywordEdit.text = "";
      this.updateContent();
   }

   updateContent()
   {
      this.refreshTreeBox();
      this.updateToolButtons();
   }
};

// ----------------------------------------------------------------------------

/**
 * Global options control group
 *
 * @param {*} parent
 */
var GlobalOptionsControl = class extends ParametersControl
{
   constructor( title, parent )
   {
      super( title, parent );

      this.parent = parent;

      //

      this.FITSCoordinateConventionComboBox = new ComboBox( this );
      this.FITSCoordinateConventionComboBox.addItem( "Global Pref" );
      this.FITSCoordinateConventionComboBox.addItem( "top-down" );
      this.FITSCoordinateConventionComboBox.addItem( "bottom-up" );
      this.FITSCoordinateConventionComboBox.toolTip = "<p>Defines the coordinate origin and orientation convention assumed by the WBPP "
         + "script for input FITS files.</p>"
         + "<p><b>Global Pref.</b>: Adopt the convention specified by global FITS format preferences.</p>"
         + "<p><b>top-down</b>: All input FITS files follow the <i>top-down</i> coordinate convention. The coordinate origin is at the "
         + "top left corner of the image, and vertical coordinates grow from top to bottom. This is the convention used by most amateur "
         + "camera control applications.</p>"
         + "<p><b>bottom-up</b>: All input FITS files follow the <i>bottom-up</i> coordinate convention. The coordinate origin is at the "
         + "bottom left corner of the image, and vertical coordinates grow from bottom to top.</p>"
         + "<p>Note that existing ROWORDER FITS keywords will always take precedence over this setting. Nonstandard ROWORDER keywords "
         + "have been supported by our FITS format module since PixInsight core version 1.8.8-6.</p>";
      this.FITSCoordinateConventionComboBox.onItemSelected = function( checked )
      {
         engine.fitsCoordinateConvention = checked;
      };

      this.FITSCoordinateConventionLabel = new Label( this );
      this.FITSCoordinateConventionLabel.text = "FITS orientation:";
      this.FITSCoordinateConventionLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;

      this.fitsCoordinateConventionSizer = new HorizontalSizer;
      this.fitsCoordinateConventionSizer.spacing = 4;
      this.fitsCoordinateConventionSizer.add( this.FITSCoordinateConventionLabel );
      this.fitsCoordinateConventionSizer.add( this.FITSCoordinateConventionComboBox );

      this.add( this.fitsCoordinateConventionSizer );

      //

      this.enableSmallGUICheckBox = new CheckBox( this );
      this.enableSmallGUICheckBox.text = "Compact GUI";
      this.enableSmallGUICheckBox.toolTip = "<p>When this option is enabled, the WBPP GUI switches to a compact layout.</p>"
         + "<p>This option may be useful on small resolution screen in order to selectively expand the controls "
         + "while reserving the maximum space possible to the groups tables.</p>";
      this.enableSmallGUICheckBox.onCheck = ( checked ) =>
      {
         engine.enableCompactGUI = checked;
         this.dialog.selfAdjustFrame();
         this.updateControls();
      }
      this.enableSmallGUICheckBox.visible = !engine.fastMode;

      this.add( this.enableSmallGUICheckBox );

      //

      this.includePathForMasterDetectionCheckBox = new CheckBox( this );
      this.includePathForMasterDetectionCheckBox.text = "Detect masters from path";
      this.includePathForMasterDetectionCheckBox.toolTip = "<p>The automatic detection of a master file is performed by searching for the word <b>master</b> "
         + "in the FITS header IMAGETYP value; if not found then the full file path is scanned, including the drive name, folders, file name and extension, "
         + "looking for the word <b>master</b> (case insensitive).</p>"
         + "<p>Uncheck this option in case your computer drive name or a folder name contains the word <b>master</b> and unintentionally causes all files to "
         + "be recognized as masters; If unchecked the file path is ignored and only the file name is scanned.</p>";
      this.includePathForMasterDetectionCheckBox.onCheck = ( checked ) =>
      {
         engine.detectMasterIncludingFullPath = checked;
         engine.rebuild();
         this.parent.dialog.refreshTreeBoxes();
      };

      this.add( this.includePathForMasterDetectionCheckBox );

      //

      this.generateRejectionMapsCheckBox = new CheckBox( this );
      this.generateRejectionMapsCheckBox.text = "Generate rejection maps";
      this.generateRejectionMapsCheckBox.toolTip = "<p>Embed the rejection maps in all generated master lights.</p>";
      this.generateRejectionMapsCheckBox.onCheck = function( checked )
      {
         engine.generateRejectionMaps = checked;
      };

      this.add( this.generateRejectionMapsCheckBox );

      //

      this.preserveWhiteBalanceCheckBox = new CheckBox( this );
      this.preserveWhiteBalanceCheckBox.text = "Preserve white balance";
      this.preserveWhiteBalanceCheckBox.toolTip = "<p>Preserves the white balance when loading CFA images, if provided by the file format.</p>";
      this.preserveWhiteBalanceCheckBox.onCheck = function( checked )
      {
         engine.preserveWhiteBalance = checked;
      };
      this.preserveWhiteBalanceCheckBox.visible = !engine.fastMode;

      this.add( this.preserveWhiteBalanceCheckBox );

      //

      this.saveSessionCheckBox = new CheckBox( this );
      this.saveSessionCheckBox.text = "Save groups on exit";
      this.saveSessionCheckBox.toolTip = "<p>When this option is selected, frame groups will be saved before closing the dialog. "
         + "They will be reloaded on next launch.</p>"
         + "<p>Select this option if you need to close WBPP and later relaunch the script "
         + "without losing the loaded file groups.</p>";
      this.saveSessionCheckBox.onCheck = function( checked )
      {
         engine.saveFrameGroups = checked;
      };

      this.add( this.saveSessionCheckBox );
      this.saveSessionCheckBox.visible = !engine.fastMode;

      //

      this.smartNamingOverrideCheckBox = new CheckBox( this );
      this.smartNamingOverrideCheckBox.text = "Smart naming override";
      this.smartNamingOverrideCheckBox.toolTip = "<p>When this option is selected, any FITS keyword "
         + "can be overridden by using the <i>smart naming syntax</i>.</p>"
         + "<p>Smart naming syntax consists of the sequence:<br/><br/>"
         + "<b>KEYWORD</b>_<b>value</b><br/><br/>"
         + "that defines a keyword name and its associated value. This sequence can be contained in "
         + "file names or full paths. When this option is enabled, the keyword values found in full "
         + "paths or file names are used, ignoring the values possibly stored in FITS headers.</p>";
      this.smartNamingOverrideCheckBox.onCheck = function( checked )
      {
         engine.smartNamingOverride = checked;
         this.parent.dialog.updateControls();
      };

      this.add( this.smartNamingOverrideCheckBox );

      //

      this.purgeExecutionCache = new PushButton( this );
      this.purgeExecutionCache.onClick = () =>
      {
         engine.executionCache.reset();
         this.updateControls();
      }
      this.purgeExecutionCache.visible = !engine.fastMode;

      this.add( this.purgeExecutionCache );

      //

      this.updateControls();
   }

   updateControls()
   {
      this.FITSCoordinateConventionComboBox.currentItem = engine.fitsCoordinateConvention;
      this.enableSmallGUICheckBox.checked = engine.enableCompactGUI;
      this.includePathForMasterDetectionCheckBox.checked = engine.detectMasterIncludingFullPath;
      this.generateRejectionMapsCheckBox.checked = engine.generateRejectionMaps;
      this.preserveWhiteBalanceCheckBox.checked = engine.preserveWhiteBalance;
      this.saveSessionCheckBox.checked = engine.saveFrameGroups;
      this.smartNamingOverrideCheckBox.checked = engine.smartNamingOverride;
      this.purgeExecutionCache.text = "Purge cache (" + WBPPUtils.readableSize( engine.executionCache.size(), 0 ) + ")";
   }
};

// ----------------------------------------------------------------------------

/**
 * Registration Reference Image control group
 *
 * @param {*} title
 * @param {*} parent
 */
var RegistrationReferenceImageControl = class extends ParametersControl
{
   constructor( title, parent )
   {
      super( title, parent );

      this.parent = parent;

      this.subframesWeightUseBestReferenceLabel = new Label( this );
      this.subframesWeightUseBestReferenceLabel.text = "Mode: ";
      this.subframesWeightUseBestReferenceLabel.setScaledFixedWidth( 32 );
      this.subframesWeightUseBestReferenceLabel.textAlignment = TextAlignment.VertCenter;

      this.subframesWeightUseBestReferenceComboBox = new ComboBox( this );
      this.subframesWeightUseBestReferenceComboBox.toolTip = "<p>Selects the method to detect the reference frame to "
         + "align the master light frames.<br/>"
         + "<br/><b>Manual</b>: Manually assign the reference frame by selecting an existing image file.<br/>"
         + "<br/><b>Auto</b>: One reference frame will be selected among all light frames and it will be used to align "
         + "all master light frames.<br/>"
         + "<br/><b>Auto, by keyword</b>: One reference frame will be selected grouping all light frames that share the "
         + "same keyword value. A different reference frame will be selected for each keyword value.<br/>"
         + "</p>";
      this.subframesWeightUseBestReferenceComboBox.onItemSelected = () =>
      {
         engine.setBestReferenceFrameMode( this.subframesWeightUseBestReferenceComboBox.currentItem )
         this.parent.dialog.updateControls();
      };

      this.updateBestReferenceComboBox();

      let subframesBestReferenceDataSizer = new HorizontalSizer;
      subframesBestReferenceDataSizer.spacing = 8;
      subframesBestReferenceDataSizer.add( this.subframesWeightUseBestReferenceLabel );
      subframesBestReferenceDataSizer.add( this.subframesWeightUseBestReferenceComboBox );
      subframesBestReferenceDataSizer.addSpacing( 22 );

      this.add( subframesBestReferenceDataSizer );

      //

      this.referenceImageEdit = new Edit( this );
      this.referenceImageEdit.toolTip = "<p>Reference image for image registration.</p>"
         + "<p>Along with selecting an existing disk file, you can double-click one of the light frames in "
         + "the Lights list to select it as the registration reference image.</p>";
      this.referenceImageEdit.onEditCompleted = function()
      {
         engine.referenceImage = this.text = File.windowsPathToUnix( this.text.trim() );
      };

      this.referenceImageSelectButton = new ToolButton( this );
      this.referenceImageSelectButton.icon = this.scaledResource( ":/icons/select-file.png" );
      this.referenceImageSelectButton.setScaledFixedSize( 20, 20 );
      this.referenceImageSelectButton.toolTip = "<p>Select the registration reference image file.</p>";
      this.referenceImageSelectButton.onClick = () =>
      {
         let ofd = new OpenFileDialog;
         ofd.multipleSelections = false;
         ofd.caption = "Select Registration Reference Image";
         ofd.loadImageFilters();
         let filters = ofd.filters;
         filters.push( [ "Comma Separated Value (CSV) files", ".csv", ".txt" ] );
         ofd.filters = filters;
         if ( ofd.execute() )
            this.referenceImageEdit.text = engine.referenceImage = ofd.filePath;
      };

      let referenceImageSizer = new HorizontalSizer;
      referenceImageSizer.add( this.referenceImageEdit );
      referenceImageSizer.addSpacing( 2 );
      referenceImageSizer.add( this.referenceImageSelectButton );

      this.add( referenceImageSizer );

      this.updateControls();
   }

   updateBestReferenceComboBox()
   {
      let combo = this.subframesWeightUseBestReferenceComboBox;
      // retrieve the available options from the engine
      let options = engine.getBestReferenceFrameModes();
      // populate the combo box with the updated list
      combo.clear();
      for ( let i = 0; i < options.length; ++i )
      {
         combo.addItem( options[ i ] );
      }
      combo.currentItem = engine.bestReferenceFrameModeIndex();
   }

   addingReferenceImage( filePath )
   {
      this.referenceImageEdit.text = filePath;
   }

   updateControls()
   {
      this.enabled = engine.imageRegistration && !engine.reuseLastReferenceFrames;
      this.updateBestReferenceComboBox();
      this.referenceImageEdit.enabled = engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL;
      this.referenceImageEdit.text = engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL ? engine.referenceImage : 'auto';
      this.referenceImageSelectButton.enabled = engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL;
   }
};

// ----------------------------------------------------------------------------

/**
 * Output Directory control group
 *
 * @param {*} title
 * @param {*} parent
 */
var OutputDirectoryControl = class extends ParametersControl
{
   constructor( title, parent )
   {
      super( title, parent );
   this.parent = parent;

   //

   this.outputDirectoryEdit = new Edit( this );
   this.outputDirectoryEdit.text = engine.outputDirectory;
   this.outputDirectoryEdit.toolTip = "<p>Output root directory.</p>"
      + "<p>The WBPP script will generate all master, calibrated and registered images "
      + "populating a directory tree rooted at the specified output directory.</p>";
   this.outputDirectoryEdit.onEditCompleted = function()
   {
      let dir = File.windowsPathToUnix( this.text.trim() );
      if ( dir.endsWith( '/' ) )
         dir = dir.substring( 0, dir.length - 1 );
      engine.outputDirectory = this.text = dir;
   };

   this.outputDirSelectButton = new ToolButton( this );
   this.outputDirSelectButton.icon = this.scaledResource( ":/icons/select-file.png" );
   this.outputDirSelectButton.setScaledFixedSize( 20, 20 );
   this.outputDirSelectButton.toolTip = "<p>Select the output root directory.</p>";
   this.outputDirSelectButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.initialPath = engine.outputDirectory;
      gdd.caption = "Select Output Directory";
      if ( gdd.execute() )
      {
         let dir = gdd.directoryPath;
         if ( dir.endsWith( '/' ) )
            dir = dir.substring( 0, dir.length - 1 );
         this.outputDirectoryEdit.text = engine.outputDirectory = dir;
      }
   };

   let outputDirSizer = new HorizontalSizer;
   outputDirSizer.add( this.outputDirectoryEdit );
   outputDirSizer.addSpacing( 2 );
   outputDirSizer.add( this.outputDirSelectButton );

   this.add( outputDirSizer );

   //

   this.updateControls = () =>
   {
      this.outputDirectoryEdit.text = engine.outputDirectory;
   }

   }
}

// ----------------------------------------------------------------------------

var OverscanSettingsControl = class extends ParametersControl
{
   constructor( parent, parentReferenceControl )
   {
      super( "Overscan Settings", parent );
   this.parentReferenceControl = parentReferenceControl;

   this.loadOverscanParametersPushButton = new PushButton( this );
   this.loadOverscanParametersPushButton.text = "LOAD FROM MASTER";
   this.loadOverscanParametersPushButton.toolTip = "<p>Loads the overscan information from the selected master file and make them active "
      + "for the current session.</p>";
   this.loadOverscanParametersPushButton.onClick = () =>
   {
      engine.calibrationMatcher.setOverscanInfoFromGroup( this.parentReferenceControl.selectedGroup );
      this.dialog.updateControls();
   }

   this.add( this.loadOverscanParametersPushButton );

   //

   this.updateWithGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }
      this.loadOverscanParametersPushButton.visible = group.hasOverscanInfo();
   }

   // hides all options
   this.hideControls = () =>
   {
      this.loadOverscanParametersPushButton.visible = false;
   };
   }
}

// ----------------------------------------------------------------------------

/**
 * Controls that contains the settings to calibrate a group.
 *
 * @param {*} parent
 */
var CalibrationSettingsControl = class extends ParametersControl
{
   constructor( parent, parentReferenceControl )
   {
      super( "Calibration Settings", parent );
   this.parentReferenceControl = parentReferenceControl;

   // -------------------------------------------------------
   // OPTIMIZE MASTER DARK DARK
   this.optimizeMasterDarkCheckBox = new CheckBox( this );
   this.optimizeMasterDarkCheckBox.text = "Optimize Master Dark";
   this.optimizeMasterDarkCheckBox.toolTip = "<p>Enable this option to apply <i>dark frame optimization</i> during calibration "
      + "of flat and light frames.</p>"
      + "<p>The dark frame optimization routine computes dark scaling factors to minimize the noise induced by dark subtraction.</p>";
   this.optimizeMasterDarkCheckBox.enabled = true;
   this.optimizeMasterDarkCheckBox.onCheck = ( checked ) =>
   {
      this.parentReferenceControl.selectedGroup.optimizeMasterDark = checked;
      this.dialog.calibrationPanelPreProcess.updateContent();
   };

   // -------------------------------------------------------
   // MASTER CHECKBOXES
   this.masterDarkCheckbox = new CheckBox( this );
   this.masterFlatCheckbox = new CheckBox( this );

   this.masterDarkCheckbox.text = "Dark:";
   this.masterFlatCheckbox.text = "Flat:";

   this.masterDarkCheckbox.setScaledFixedWidth( 50 );
   this.masterFlatCheckbox.setScaledFixedWidth( 50 );

   this.masterDarkCheckbox.onCheck = ( checked ) =>
   {
      this.parentReferenceControl.selectedGroup.forceNoDark = !checked;
      if ( !checked )
         this.parentReferenceControl.selectedGroup.optimizeMasterDark = false;

      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };
   this.masterFlatCheckbox.onCheck = ( checked ) =>
   {
      this.parentReferenceControl.selectedGroup.forceNoFlat = !checked;
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };

   // -------------------------------------------------------
   // MASTER COMBO BOXES
   this.masterDarkCombo = new ComboBox( this );
   this.masterFlatCombo = new ComboBox( this );

   // assign the override group preference or clear it
   this.masterDarkCombo.onItemSelected = ( itemIndex ) =>
   {
      // group change, need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      if ( itemIndex == 0 )
         selectedGroup.overrideDark = undefined;
      else
         selectedGroup.overrideDark = this.masterDarkCombo.__groups__[ itemIndex - 1 ];
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };

   // assign the override group preference or clear it
   this.masterFlatCombo.onItemSelected = ( itemIndex ) =>
   {
      // group change, need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      if ( itemIndex == 0 )
         selectedGroup.overrideFlat = undefined;
      else
         selectedGroup.overrideFlat = this.masterFlatCombo.__groups__[ itemIndex - 1 ];
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };

   // -------------------------------------------------------
   // LAYOUT THE masters checkbox and dropdown
   let darkSizer = new HorizontalSizer;
   darkSizer.spacing = 4;
   darkSizer.add( this.masterDarkCheckbox );
   darkSizer.add( this.masterDarkCombo );

   let flatSizer = new HorizontalSizer;
   flatSizer.spacing = 4;
   flatSizer.add( this.masterFlatCheckbox );
   flatSizer.add( this.masterFlatCombo );

   // -------------------------------------------------------
   // LAYOUT THE CONTROLS
   this.add( darkSizer );
   this.add( flatSizer );
   this.add( this.optimizeMasterDarkCheckBox );

   // -------------------------------------------------------
   // HELPERS

   // the control gets updated given the group
   this.updateWithGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }
      this.showControlsForGroup( group );
      this.masterDarkCheckbox.checked = !group.forceNoDark;
      this.masterFlatCheckbox.checked = !group.forceNoFlat;
      this.optimizeMasterDarkCheckBox.checked = group.optimizeMasterDark;
      this.optimizeMasterDarkCheckBox.enabled = this.masterDarkCheckbox.checked;
   };

   // show/hide the proper options depending on the given group
   this.showControlsForGroup = ( group ) =>
   {
      if ( !group )
         return;

      this.masterDarkCheckbox.visible = !group.hasMaster && ( group.imageType == ImageType.Flat || group.imageType == ImageType.Light );
      this.masterFlatCheckbox.visible = ( group.imageType == ImageType.Light );

      this.masterDarkCombo.visible = this.masterDarkCheckbox.visible;
      this.masterFlatCombo.visible = this.masterFlatCheckbox.visible;

      this.optimizeMasterDarkCheckBox.visible = !group.hasMaster && ( group.imageType == ImageType.Flat || group.imageType == ImageType.Light );

      if ( this.masterDarkCombo.visible )
         this.enableDarkFor( group );

      if ( this.masterFlatCombo.visible )
         this.enableFlatFor( group );
   };

   // hides all options
   this.hideControls = () =>
   {
      this.masterDarkCheckbox.visible = false;
      this.masterFlatCheckbox.visible = false;
      this.masterDarkCombo.visible = false;
      this.masterFlatCombo.visible = false;
      this.optimizeMasterDarkCheckBox.visible = false;
   };

   // prepare the Dark dropdown populating the compatible master darks for the given group
   this.enableDarkFor = ( group ) =>
   {
      // get compatible darks
      let groupList = engine.calibrationMatcher.getCalibrationGroupsMatching(
      {
         imageType: ImageType.Dark,
         binning: group.binning,
         size: group.size
      } );
      // empty the list
      this.masterDarkCombo.clear();
      // fill the list
      this.masterDarkCombo.addItem( "Auto" );
      groupList.forEach( group => this.masterDarkCombo.addItem( "#" + group.__counter__ + ": " + group.dropdownShortString() ) );
      this.masterDarkCombo.__groups__ = groupList;

      if ( group.overrideDark )
      {
         for ( let i = 0; i < groupList.length; ++i )
            if ( groupList[ i ].id == group.overrideDark.id )
            {
               this.masterDarkCombo.currentItem = i + 1;
               break;
            }
      }
      else
         this.masterDarkCombo.currentItem = 0;

      // optimize master dark checkbox
      this.optimizeMasterDarkCheckBox.checked = group.optimizeMasterDark;
   };

   // prepare the Flat dropdown populating the compatible master flats for the given group
   this.enableFlatFor = ( group ) =>
   {
      // get compatible Flats
      let groupList = engine.calibrationMatcher.getCalibrationGroupsMatching(
      {
         imageType: ImageType.Flat,
         binning: group.binning,
         size: group.size,
         isCFA: group.isCFA
      } );
      // empty the list
      this.masterFlatCombo.clear();
      // fill the list
      this.masterFlatCombo.addItem( "Auto" );
      groupList.forEach( group => this.masterFlatCombo.addItem( "#" + group.__counter__ + ": " + group.dropdownShortString() ) );
      this.masterFlatCombo.__groups__ = groupList;

      if ( group.overrideFlat )
      {
         for ( let i = 0; i < groupList.length; ++i )
            if ( group.overrideFlat && groupList[ i ].id == group.overrideFlat.id )
            {
               this.masterFlatCombo.currentItem = i + 1;
               break;
            }
      }
      else
         this.masterFlatCombo.currentItem = 0;
   };

   // start with all options hidden
   this.hideControls();
   }
}

/**
 * Controls that contains the pedestal settings of a calibration group.
 *
 * @param {*} parent
 */
var PedestalSettingsControl = class extends ParametersControl
{
   constructor( parent, parentReferenceControl )
   {
      super( "Output Pedestal Settings", parent );
   this.parentReferenceControl = parentReferenceControl;

   let labelWidth = this.font.width( "Value (DN):m" );

   // -------------------------------------------------------
   // LIGHT OUTPUT PEDESTAL MODE
   let pedestalModeTooltip = "<p>This parameter defines how to calculate and apply output pedestals.</p>"
      + "<p><b>Literal value</b> allows you to specify a pedestal value in 16-bit data number units (DN) with the "
      + "<i>output pedestal</i> parameter.</p>"
      + "<p><b>Automatic</b> will apply an automatically calculated pedestal value to frames that have negative, zero "
      + "or insignificant (to machine epsilon) minimum pixel values after calibration. Automatic pedestals can be used "
      + "to ensure positivity of the calibrated image with minimal truncation.</p>"
      + "<p>See also the <i>limit</i> and <i>value</i> parameters for more information.</p>";

   this.pedestalModeLabel = new Label( this );
   this.pedestalModeLabel.text = "Mode:";
   this.pedestalModeLabel.setFixedWidth( labelWidth );
   this.pedestalModeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.pedestalModeLabel.toolTip = pedestalModeTooltip;

   this.pedestalModeComboBox = new ComboBox( this );
   this.pedestalModeComboBox.toolTip = pedestalModeTooltip;
   this.pedestalModeComboBox.addItem( "Literal value" );
   this.pedestalModeComboBox.addItem( "Automatic" );

   this.pedestalModeComboBox.onItemSelected = ( value ) =>
   {
      // local group change, no need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      selectedGroup.lightOutputPedestalMode = value;
      this.parentReferenceControl._treeBoxRowSelectionUpdated( this.parentReferenceControl.selectedNode.parentTree );
   };

   // -------------------------------------------------------
   // LIGHT OUTPUT PEDESTAL VALUE
   let lightOutputPedestalTooltip = "<p>The <i>output pedestal</i> is a small quantity expressed in "
      + "the 16-bit unsigned integer range (from 0 to 65535). It is added at the end of the calibration process "
      + "and its purpose is to prevent negative values that can occur sometimes as a result of overscan and bias "
      + "subtraction. Under normal conditions, you should need no pedestal to calibrate science frames because "
      + "mean sky background levels should be sufficiently high as to avoid negative values. The default value is zero.</p>";

   this.lightOutputPedestalLabel = new Label( this );
   this.lightOutputPedestalLabel.text = "Value (DN):";
   this.lightOutputPedestalLabel.setFixedWidth( labelWidth );
   this.lightOutputPedestalLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.lightOutputPedestalLabel.toolTip = lightOutputPedestalTooltip;

   this.lightOutputPedestalSpinBox = new SpinBox( this );
   this.lightOutputPedestalSpinBox.minValue = 0;
   this.lightOutputPedestalSpinBox.maxValue = 999;
   this.lightOutputPedestalSpinBox.toolTip = lightOutputPedestalTooltip;

   this.lightOutputPedestalSpinBox.onValueUpdated = ( value ) =>
   {
      // local group change, no need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      selectedGroup.lightOutputPedestal = value;
      this.parentReferenceControl._treeBoxRowSelectionUpdated( this.parentReferenceControl.selectedNode.parentTree );
   };

   // -------------------------------------------------------
   // LIGHT OUTPUT PEDESTAL THRESHOLD
   let lightOutputPedestalLimitTooltip = "<p>Maximum fraction of negative or insignificant calibrated pixels allowed "
      + "in automatic pedestal generation mode.</p>"
      + "<p>This parameter represents a fraction of the total image pixels in the [0,1] range. When the image has more than this "
      + "fraction of negative or insignificant pixel values after calibration and the <i>output pedestal mode</i> is set to <i>automatic</i>, "
      + "the process will generate an additive pedestal to ensure that no more than this fraction of negative or insignificant pixels will be "
      + "present in the calibrated image.</p>"
      + "<p>The default value is 0.0001, which represents a 0.01% of the total pixels.</p>";

   this.lightOutputPedestalLimitControl = new NumericEdit( this );
   this.lightOutputPedestalLimitControl.label.text = "Limit:";
   this.lightOutputPedestalLimitControl.label.setFixedWidth( labelWidth );
   this.lightOutputPedestalLimitControl.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.lightOutputPedestalLimitControl.label.toolTip = lightOutputPedestalLimitTooltip;
   this.lightOutputPedestalLimitControl.edit.setVariableWidth();
   this.lightOutputPedestalLimitControl.setReal( true );
   this.lightOutputPedestalLimitControl.setRange( 0, 0.01 );
   this.lightOutputPedestalLimitControl.setPrecision( 5 );


   this.lightOutputPedestalLimitControl.toolTip = lightOutputPedestalLimitTooltip;

   this.lightOutputPedestalLimitControl.onValueUpdated = ( value ) =>
   {
      // local group change, no need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      selectedGroup.lightOutputPedestalLimit = value;
      this.parentReferenceControl._treeBoxRowSelectionUpdated( this.parentReferenceControl.selectedNode.parentTree );
   };

   // -------------------------------------------------------
   // APPLY TO ALL LIGHT FRAMES
   this.pedestalLimitApplyToAllButton = new PushButton( this );
   this.pedestalLimitApplyToAllButton.text = "Apply to all light frames";
   this.pedestalLimitApplyToAllButton.toolTip = "Apply the output pedestal limit value of the current group to all other groups.";
   this.pedestalLimitApplyToAllButton.onClick = () =>
   {
      // local groups change, no need to rebuild
      let selectedGroup = this.parentReferenceControl.selectedGroup;
      engine.parametersManager.applyOutputPedestalLimit( selectedGroup.lightOutputPedestalMode, selectedGroup.lightOutputPedestal, selectedGroup.lightOutputPedestalLimit );
      this.parentReferenceControl._treeBoxRowSelectionUpdated( this.parentReferenceControl.selectedNode.parentTree );
   };

   //

   let pedestalModeSizer = new HorizontalSizer;
   pedestalModeSizer.spacing = 4;
   pedestalModeSizer.add( this.pedestalModeLabel );
   pedestalModeSizer.add( this.pedestalModeComboBox, 100 );

   let outputPedestalSizer = new HorizontalSizer;
   outputPedestalSizer.spacing = 4;
   outputPedestalSizer.add( this.lightOutputPedestalLabel );
   outputPedestalSizer.add( this.lightOutputPedestalSpinBox );
   outputPedestalSizer.addStretch();

   let outputPedestalLimitSizer = new HorizontalSizer;
   outputPedestalLimitSizer.add( this.lightOutputPedestalLimitControl );
   outputPedestalLimitSizer.addStretch();

   this.add( pedestalModeSizer );
   this.add( outputPedestalSizer );
   this.add( outputPedestalLimitSizer );
   this.add( this.pedestalLimitApplyToAllButton );

   // -------------------------------------------------------
   // HELPERS

   // the control gets updated given the group
   this.updateWithGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }

      this.showControlsForGroup( group );
      let pedestalModeAuto = group.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Auto;
      this.lightOutputPedestalSpinBox.value = pedestalModeAuto ? 0 : group.lightOutputPedestal;
      this.pedestalModeComboBox.currentItem = group.lightOutputPedestalMode;
      this.lightOutputPedestalLimitControl.setValue( group.lightOutputPedestalLimit );

      this.lightOutputPedestalLabel.enabled = group.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Literal;
      this.lightOutputPedestalSpinBox.enabled = group.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Literal;
      this.lightOutputPedestalLimitControl.enabled = group.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Auto;
   };

   // show/hide the proper options depending on the given group
   this.showControlsForGroup = ( group ) =>
   {
      if ( !group )
         return;

      this.pedestalModeLabel.visible = group.imageType == ImageType.Light;
      this.pedestalModeComboBox.visible = group.imageType == ImageType.Light;

      this.lightOutputPedestalLabel.visible = group.imageType == ImageType.Light;
      this.lightOutputPedestalSpinBox.visible = group.imageType == ImageType.Light;

      this.lightOutputPedestalLimitControl.visible = group.imageType == ImageType.Light;
      this.pedestalLimitApplyToAllButton.visible = group.imageType == ImageType.Light;
   };

   // hides all options
   this.hideControls = () =>
   {
      this.pedestalModeLabel.visible = false;
      this.pedestalModeComboBox.visible = false;
      this.lightOutputPedestalLabel.visible = false;
      this.lightOutputPedestalSpinBox.visible = false;
      this.lightOutputPedestalLimitControl.visible = false;
      this.pedestalLimitApplyToAllButton.visible = false;
   };

   // start with all options hidden
   this.hideControls();
   }
}

/**
 * Controls that contains the cosmetic correction settings of a calibration group.
 *
 * @param {*} parent
 */
var CosmeticCorrectionSettingsControl = class extends ParametersControl
{
   constructor( parent, parentReferenceControl )
   {
      super( "Cosmetic Correction", parent );
   this.parentReferenceControl = parentReferenceControl;

   let labelWidth = this.font.width( "High Sigma:m" );

   // -------------------------------------------------------
   // Cosmetic Correction template icon
   let enabledToolTip =
      "<p>The automatic cosmetic correction feature detects pixels with abnormally high or low "
      + "values in the master dark frame using multiscale and statistical analysis techniques. "
      + "These pixels are then replaced with plausible values calculated from their local "
      + "neighborhoods during the image calibration task.</p>";

   let highSigmaToolTip =
      "<p>When the automatic mode is enabled, this parameter defines a threshold in sigma units "
      + "above the median of a high-pass filtered master dark frame. Pixels above this threshold "
      + "are considered <i>hot pixels</i> and tagged for cosmetic correction during the image "
      + "calibration task. Decrease the value of this parameter to select more potential hot pixels. "
      + "The default value is 10.</p>";

   this.CCEnabledCheckBox = new CheckBox( this );
   this.CCEnabledCheckBox.text = "Automatic";
   this.CCEnabledCheckBox.toolTip = enabledToolTip;
   this.CCEnabledCheckBox.onCheck = ( value ) =>
   {
      this.parentReferenceControl.selectedGroup.enableCC( value );
      this.dialog.calibrationPanelPreProcess.updateContent();
   }

   let enabledSizer = new HorizontalSizer;
   enabledSizer.spacing = 4;
   enabledSizer.addUnscaledSpacing( labelWidth + 4 );
   enabledSizer.add( this.CCEnabledCheckBox );

   this.CCHighSigmaNumericControl = new NumericControl( this );
   this.CCHighSigmaNumericControl.label.text = "High sigma:";
   this.CCHighSigmaNumericControl.label.setFixedWidth( labelWidth );
   this.CCHighSigmaNumericControl.setRange( 1, 100 );
   this.CCHighSigmaNumericControl.slider.setRange( 1, 100 );
   this.CCHighSigmaNumericControl.setPrecision( 0 );
   this.CCHighSigmaNumericControl.toolTip = highSigmaToolTip;
   this.CCHighSigmaNumericControl.onValueUpdated = ( value ) =>
   {
      this.parentReferenceControl.selectedGroup.setCcHighSigma( value );
      this.dialog.calibrationPanelPreProcess.updateContent();
   };

   let templateIconIdToolTip = "<p>Identifier of an existing CosmeticCorrection icon "
      + "that will be used as a template to apply a cosmetic correction process to the "
      + "calibrated frames. Cosmetic correction will be applied just after calibration, "
      + "before deBayering (when appropriate) and registration.</p>";

   this.CCTemplateLabel = new Label( this );
   this.CCTemplateLabel.text = "Template:";
   this.CCTemplateLabel.setFixedWidth( labelWidth );
   this.CCTemplateLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.CCTemplateLabel.toolTip = templateIconIdToolTip;

   this.CCTemplateComboBox = new ComboBox( this );
   this.CCTemplateComboBox.toolTip = templateIconIdToolTip;
   this.CCTemplateComboBox.addItem( "<none>" );
   let icons = ProcessInstance.iconsByProcessId( "CosmeticCorrection" ).sort( ( a, b ) => ( a.toUpperCase().localeCompare( b.toUpperCase() ) ) );
   for ( let i = 0; i < icons.length; ++i )
      this.CCTemplateComboBox.addItem( icons[ i ] );

   this.CCTemplateComboBox.onItemSelected = ( value ) =>
   {
      // group change, need to rebuild
      this.parentReferenceControl.selectedGroup.ccData.CCTemplate = value == 0 ? "" : this.CCTemplateComboBox.itemText( value );
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
   }

   let CCTemplateSizer = new HorizontalSizer;
   CCTemplateSizer.spacing = 4;
   CCTemplateSizer.add( this.CCTemplateLabel );
   CCTemplateSizer.add( this.CCTemplateComboBox );

   // -------------------------------------------------------
   // APPLY TO ALL LIGHT FRAMES
   this.CCApplyToAllButton = new PushButton( this );
   this.CCApplyToAllButton.text = "Apply to all groups";
   this.CCApplyToAllButton.toolTip = "<p>Apply the current cosmetic correction parameters to all groups.</p>";
   this.CCApplyToAllButton.onClick = () =>
   {
      engine.parametersManager.applyCCData( this.parentReferenceControl.selectedGroup.ccData );
      this.dialog.calibrationPanelPreProcess.updateContent();
   };

   //

   this.add( enabledSizer );
   this.add( this.CCHighSigmaNumericControl );
   this.add( CCTemplateSizer );
   this.add( this.CCApplyToAllButton );

   // -------------------------------------------------------
   // HELPERS

   // the control gets updated given the group
   this.updateWithGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }

      this.showControlsForGroup( group );

      this.CCEnabledCheckBox.checked = group.ccData.enabled;
      this.CCHighSigmaNumericControl.setValue( group.ccData.highSigma );
      this.CCHighSigmaNumericControl.enabled = group.ccData.enabled;
      let currentItem = 0;
      for ( let i = 1; i < this.CCTemplateComboBox.numberOfItems; ++i )
      {
         if ( this.CCTemplateComboBox.itemText( i ) == group.ccData.CCTemplate )
         {
            currentItem = i;
            break;
         }
      }
      this.CCTemplateComboBox.currentItem = currentItem;
      this.CCTemplateComboBox.enabled = !group.ccData.enabled;
   };

   // show/hide the proper options depending on the given group
   this.showControlsForGroup = ( group ) =>
   {
      if ( !group )
         return;

      this.CCTemplateLabel.visible = group.imageType == ImageType.Light;
      this.CCTemplateComboBox.visible = group.imageType == ImageType.Light;
      this.CCEnabledCheckBox.visible = group.imageType == ImageType.Light;
      this.CCHighSigmaNumericControl.visible = group.imageType == ImageType.Light;
      this.CCApplyToAllButton.visible = group.imageType == ImageType.Light;
   };

   // hides all options
   this.hideControls = () =>
   {
      this.CCTemplateLabel.visible = false;
      this.CCTemplateComboBox.visible = false;
      this.CCEnabledCheckBox.visible = false;
      this.CCHighSigmaNumericControl.visible = false;
      this.CCApplyToAllButton.visible = false;
   };

   // start with all options hidden
   this.hideControls();
   }
}

/**
 * Control that contains the debayer settings of a group
 */

var DebayerSettingsControl = class extends ParametersControl
{
   constructor( parent, parentReferenceControl )
   {
      super( "CFA Settings", parent );
   this.parentReferenceControl = parentReferenceControl;

   let labelWidth1 = this.font.width( "DeBayer method:" + "T" );

   // -------------------------------------------------------
   // IS CFA
   let cfaImagesToolTip =
      "<p>When checked, the WBPP script works under the assumption that all "
      + "the frames in this group (calibration and light frames) have been mosaiced "
      + "with a Color Filter Array (CFA) pattern, such as a Bayer pattern. When this "
      + "option is enabled, an additional deBayering task will be performed on light "
      + "frames prior to image registration using the <i>Mosaic pattern</i> and "
      + "<i>DeBayer method</i> parameters.</p>";

   this.isCFALabel = new Label( this );
   this.isCFALabel.text = "CFA images:";
   this.isCFALabel.setFixedWidth( labelWidth1 );
   this.isCFALabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.isCFALabel.toolTip = cfaImagesToolTip;

   this.isCFACheckBox = new CheckBox( this );
   this.isCFACheckBox.text = "";
   this.isCFACheckBox.toolTip = cfaImagesToolTip;
   this.isCFACheckBox.enabled = true;
   this.isCFACheckBox.onCheck = ( checked ) =>
   {
      // update the group property and rebuild the pipeline
      this.parentReferenceControl.selectedGroup.isCFA = checked;
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.calibrationPanelPostProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };
   let isCFACheckBoxSizer = new HorizontalSizer;
   isCFACheckBoxSizer.spacing = 4;
   isCFACheckBoxSizer.add( this.isCFALabel );
   isCFACheckBoxSizer.add( this.isCFACheckBox );

   // -------------------------------------------------------
   // BAYER PATTERN
   this.bayerPatternLabel = new Label( this );
   this.bayerPatternLabel.text = "Mosaic pattern:";
   this.bayerPatternLabel.setFixedWidth( labelWidth1 );
   this.bayerPatternLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.bayerPatternComboBox = new ComboBox( this );
   this.bayerPatternComboBox.addItem( "Auto" );
   this.bayerPatternComboBox.addItem( "RGGB" );
   this.bayerPatternComboBox.addItem( "BGGR" );
   this.bayerPatternComboBox.addItem( "GBRG" );
   this.bayerPatternComboBox.addItem( "GRBG" );
   this.bayerPatternComboBox.addItem( "GRGB" );
   this.bayerPatternComboBox.addItem( "GBGR" );
   this.bayerPatternComboBox.addItem( "RGBG" );
   this.bayerPatternComboBox.addItem( "BGRG" );
   this.bayerPatternComboBox.onItemSelected = ( itemIndex ) =>
   {
      // CFA pattern affects only the visual information of the current row
      this.parentReferenceControl.selectedGroup.CFAPattern = itemIndex;
      this.parentReferenceControl.updateSelectedRow();
   };

   this.bayerPatternSizer = new HorizontalSizer;
   this.bayerPatternSizer.spacing = 4;
   this.bayerPatternSizer.add( this.bayerPatternLabel );
   this.bayerPatternSizer.add( this.bayerPatternComboBox, 100 );

   //

   this.debayerMethodLabel = new Label( this );
   this.debayerMethodLabel.text = "DeBayer method:";
   this.debayerMethodLabel.setFixedWidth( labelWidth1 );
   this.debayerMethodLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.debayerMethodComboBox = new ComboBox( this );
   this.debayerMethodComboBox.addItem( "SuperPixel" );
   this.debayerMethodComboBox.addItem( "Bilinear" );
   this.debayerMethodComboBox.addItem( "VNG" );
   this.debayerMethodComboBox.onItemSelected = ( itemIndex ) =>
   {
      // update the group property and rebuild the pipeline
      this.parentReferenceControl.selectedGroup.debayerMethod = itemIndex;
      engine.rebuild();
      this.dialog.calibrationPanelPreProcess.updateContent();
      this.dialog.calibrationPanelPostProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };

   this.debayerMethodSizer = new HorizontalSizer;
   this.debayerMethodSizer.spacing = 4;
   this.debayerMethodSizer.add( this.debayerMethodLabel );
   this.debayerMethodSizer.add( this.debayerMethodComboBox, 100 );

   // -------------------------------------------------------

   this.cfaSettingsApplyToAllButton = new PushButton( this );
   this.cfaSettingsApplyToAllButton.text = "Apply globally";
   this.cfaSettingsApplyToAllButton.toolTip = "<p>Apply the Debayer settings of the "
      + "current group to the rest of the groups in the project.</p>";
   this.cfaSettingsApplyToAllButton.onClick = () =>
   {
      let imageType = this.parentReferenceControl.selectedGroup.imageType;
      let response = new MessageBox( "<p>This operation will apply the same CFA settings of the selected group to all "
         + StackEngine.imageTypeToString( imageType ) + " groups in the session. Do you want to proceed?</p>",
         "Apply CFA Settings", StdIcon.Question, StdButton.Yes, StdButton.No ).execute();
      if ( response == StdButton.Yes )
      {
         let imageType = this.parentReferenceControl.selectedGroup.imageType;
         engine.parametersManager.applyCFASettings( imageType, this.isCFACheckBox.checked, this.bayerPatternComboBox.currentItem, this.debayerMethodComboBox.currentItem );
         engine.rebuild();
         this.dialog.calibrationPanelPreProcess.updateContent();
         this.dialog.calibrationPanelPostProcess.updateContent();
         this.dialog.pipelinePanel.updateContent();
      }
   };

   // -------------------------------------------------------
   // LAYOUT THE CONTROLS
   this.add( isCFACheckBoxSizer );
   this.add( this.bayerPatternSizer );
   this.add( this.debayerMethodSizer );
   this.add( this.cfaSettingsApplyToAllButton );

   // -------------------------------------------------------
   // HELPERS
   this.updateWithGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }

      this.showControlsForGroup( group );
      this.isCFACheckBox.checked = group.isCFA;
      this.bayerPatternComboBox.currentItem = group.CFAPattern;
      this.debayerMethodComboBox.currentItem = group.debayerMethod;
   };

   this.showControlsForGroup = ( group ) =>
   {
      if ( !group )
      {
         this.hideControls();
         return;
      }

      this.isCFACheckBox.visible = ( group.imageType == ImageType.Flat || group.imageType == ImageType.Light );
      this.isCFALabel.visible = this.isCFACheckBox.visible;
      this.bayerPatternComboBox.visible = group.imageType == ImageType.Light;
      this.debayerMethodComboBox.visible = group.imageType == ImageType.Light;
      this.bayerPatternLabel.visible = this.bayerPatternComboBox.visible;
      this.debayerMethodLabel.visible = this.debayerMethodComboBox.visible;
      this.cfaSettingsApplyToAllButton.visible = this.isCFACheckBox.visible;

      this.bayerPatternComboBox.enabled = group.isCFA;
      this.debayerMethodComboBox.enabled = group.isCFA;

      this.cfaSettingsApplyToAllButton.text = ( group.imageType == ImageType.Light ) ? "Apply to all light frames" : "Apply to all flat frames";
   };

   this.hideControls = () =>
   {
      this.isCFACheckBox.visible = false;
      this.isCFALabel.visible = false;
      this.bayerPatternLabel.visible = false;
      this.debayerMethodLabel.visible = false;
      this.bayerPatternComboBox.visible = false;
      this.debayerMethodComboBox.visible = false;
      this.cfaSettingsApplyToAllButton.visible = false;
   };

   this.hideControls();
   }
}

// -----------------------------------------------------------------------------

/**
 * Base dialog that properly resizes on small screens
 *
 */
var WBPPDialog = class extends Dialog
{
   constructor()
   {
      super();

      this.center = ( width, height ) =>
      {
         let origin = new Point(
            Math.max( 0, ( this.availableScreenRect.width - width ) / 2 ),
            Math.max( 0, ( this.availableScreenRect.height - height ) / 2 ) );

         this.move( origin );
      }
   }
}

// -----------------------------------------------------------------------------
/**
 * This dialog depicts the calibration flow diagram for the specified groups
 * and options.
 *
 * The calibration flow is generically represented by a group (light) that
 * needs to be bias-subtracted, dark-subtracted and flat-divided. If dark is
 * marked to be calibrated then the bias is subtracted to the Dark before
 * subtracting the dark from the light. If Dark needs to be optimized then the
 * dark is multiplied by a proper constant before being subtracted from the
 * light (but after the bias subtraction).
 */
var CalibrationFlowDialog = class extends WBPPDialog
{
   constructor( bias, dark, flat, light, darkIsOptimized )
   {
      super();

   // dynamic window sizing
   this.layoutTimer = new Timer( 0 /*interval*/ , false /*periodic*/ );
   this.layoutTimer.onTimeout = () =>
   {
      let rect = this.graphRect.inflatedBy( this.logicalPixelsToPhysical( 16 ) );
      this.graph.setFixedSize( rect.width, rect.height );
      this.ensureLayoutUpdated();
      this.adjustToContents();
      this.setFixedSize();
   };

   // title
   this.label = new Label( this );
   this.label.text = light ? "<b>Calibration Flow Diagram</b><br/>" + light.toString() : "";
   this.label.textAlignment = TextAlignment.Center;
   this.label.useRichText = true;

   // graph
   this.graphGenerator = new GraphGenerator( this );
   this.graph = new ScrollBox( this );
   this.graph.backgroundColor = 0xFFFFFFFF;
   this.graph.viewport.onPaint = ( x0, y0, x1, y1 ) =>
   {
      this.graphRect = this.graphGenerator.generateGraph( this.graph.viewport, bias, dark, flat, light, darkIsOptimized );
      // Schedule a single timer event that will be delivered as soon as we
      // return to the event loop. This is necessary because we cannot layout
      // the control from an onPaint() event handler, since doing that would
      // lead to infinite recursion.
      this.layoutTimer.start();
   };

   // layout
   this.sizer = new VerticalSizer;
   this.sizer.margin = 8;
   this.sizer.add( this.label );
   this.sizer.addSpacing( 8 );
   this.sizer.add( this.graph );
   }
}

// ----------------------------------------------------------------------------

/**
 * Controls that shows the controls for the post processing configurations
 *
 * @param {*} parent
 */
var PostProcessingConfiguration = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Channels configuration", parent );

   let labelWidth = this.font.width( "MMMMMM: " );

   //

   this.debayerOutputLabel = new Label( this );
   this.debayerOutputLabel.text = "Debayer:";
   this.debayerOutputLabel.setFixedWidth( labelWidth );
   this.debayerOutputLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.debayerOutputComboBox = new ComboBox( this );
   this.debayerOutputComboBox.addItem( "Combined RGB" );
   this.debayerOutputComboBox.addItem( "Separate RGB" );
   this.debayerOutputComboBox.addItem( "Combined + Separate" );
   this.debayerOutputComboBox.onItemSelected = ( item ) =>
   {
      engine.debayerOutputMethod = item;
      parent.dialog.updateControls();
      this.updateContent();
   };

   this.debayerOutputComboBox.toolTip = this.debayerOutputLabel.toolTip =
      "<p>Demosaiced/interpolated images can be generated as combined RGB color images, "
      + "as separate RGB channels stored as monochrome images, or applying both options at the same time.</p>"
      + "<p>Generation of single RGB color images is the default option.<br/>"
      + "Separate RGB channel images can be useful for correction of non-isotropic channel misalignments "
      + "such as those caused by chromatic aberration and atmospheric dispersion, by computing image registration "
      + "transformations with distortion correction among all color components of a data set. This procedure is "
      + "compatible with normal image integrations as well as drizzle integrations.</p>"
      + "<p>Separate channel file names will carry the _R, _G and _B suffixes, respectively for the red, green and blue components.</p>";

   this.debayerOutputSizer = new HorizontalSizer;
   this.debayerOutputSizer.spacing = 4;
   this.debayerOutputSizer.add( this.debayerOutputLabel );
   this.debayerOutputSizer.add( this.debayerOutputComboBox, 100 );

   //

   this.activeChannelsLabel = new Label( this );
   this.activeChannelsLabel.text = "Active:";
   this.activeChannelsLabel.setFixedWidth( labelWidth );
   this.activeChannelsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.activeChannelRCheckBox = new CheckBox( this );
   this.activeChannelRCheckBox.text = "R";
   this.activeChannelRCheckBox.onCheck = ( value ) =>
   {
      // cannot uncheck the last channel, at least one must be active
      if ( !value && !engine.debayerActiveChannelG && !engine.debayerActiveChannelB )
      {
         this.activeChannelRCheckBox.checked = true;
         return;
      }

      engine.debayerActiveChannelR = value;
      parent.dialog.updateControls();
      this.updateContent();
   }

   this.activeChannelGCheckBox = new CheckBox( this );
   this.activeChannelGCheckBox.text = "G";
   this.activeChannelGCheckBox.onCheck = ( value ) =>
   {
      // cannot uncheck the last channel, at least one must be active
      if ( !value && !engine.debayerActiveChannelR && !engine.debayerActiveChannelB )
      {
         this.activeChannelGCheckBox.checked = true;
         return;
      }

      engine.debayerActiveChannelG = value;
      parent.dialog.updateControls();
      this.updateContent();
   }

   this.activeChannelBCheckBox = new CheckBox( this );
   this.activeChannelBCheckBox.text = "B";
   this.activeChannelBCheckBox.onCheck = ( value ) =>
   {
      // cannot uncheck the last channel, at least one must be active
      if ( !value && !engine.debayerActiveChannelR && !engine.debayerActiveChannelG )
      {
         this.activeChannelBCheckBox.checked = true;
         return;
      }

      engine.debayerActiveChannelB = value;
      parent.dialog.updateControls();
      this.updateContent();
   }

   let activeChannelSizer = new HorizontalSizer;
   activeChannelSizer.spacing = 4;
   activeChannelSizer.add( this.activeChannelsLabel );
   activeChannelSizer.add( this.activeChannelRCheckBox );
   activeChannelSizer.addSpacing( 8 );
   activeChannelSizer.add( this.activeChannelGCheckBox );
   activeChannelSizer.addSpacing( 8 );
   activeChannelSizer.add( this.activeChannelBCheckBox );
   activeChannelSizer.addStretch();

   //

   this.recombineRGBCheckBox = new CheckBox( this );
   this.recombineRGBCheckBox.text = "Recombine RGB";
   this.recombineRGBCheckBox.onCheck = ( checked ) =>
   {
      engine.recombineRGB = checked;
      parent.dialog.updateControls();
      this.updateContent();
   }

   let dummy = new Label( this );
   dummy.setFixedWidth( labelWidth );

   let recombineRGBSizer = new HorizontalSizer;
   recombineRGBSizer.spacing = 4;
   recombineRGBSizer.addSpacing( 4 );
   recombineRGBSizer.add( dummy );
   recombineRGBSizer.add( this.recombineRGBCheckBox );
   recombineRGBSizer.addStretch();

   // layout
   this.add( this.debayerOutputSizer );
   this.add( activeChannelSizer );
   this.add( recombineRGBSizer );

   this.updateContent = () =>
   {
      this.debayerOutputComboBox.currentItem = engine.debayerOutputMethod;

      this.activeChannelRCheckBox.checked = engine.debayerActiveChannelR;
      this.activeChannelGCheckBox.checked = engine.debayerActiveChannelG;
      this.activeChannelBCheckBox.checked = engine.debayerActiveChannelB;
      this.activeChannelRCheckBox.enabled = engine.debayerOutputMethod != BPP.DebayerOutputMode.COMBINED;
      this.activeChannelGCheckBox.enabled = engine.debayerOutputMethod != BPP.DebayerOutputMode.COMBINED;
      this.activeChannelBCheckBox.enabled = engine.debayerOutputMethod != BPP.DebayerOutputMode.COMBINED;

      this.recombineRGBCheckBox.checked = engine.recombineRGB;
      this.recombineRGBCheckBox.enabled =
         engine.integrate
         && engine.debayerOutputMethod != BPP.DebayerOutputMode.COMBINED
         && engine.debayerActiveChannelR
         && engine.debayerActiveChannelG
         && engine.debayerActiveChannelB;
   }

   this.updateContent();
   }
}

// ----------------------------------------------------------------------------

/**
 * Controls that shows the Drizzle configurations for a post-process group
 *
 * @param {*} parent
 */
var DrizzleConfiguration = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Drizzle configuration", parent );

   let labelWidth = this.font.width( "MMMMMMM: " );

   //

   let enableTooltip = "<p>Enables drizzle integration for the selected group.</p>";

   this.enableLabel = new Label( this );
   this.enableLabel.text = "Enable:";
   this.enableLabel.setFixedWidth( labelWidth );
   this.enableLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.enableLabel.toolTip = enableTooltip;

   this.enableCheckbox = new CheckBox( this );
   this.enableCheckbox.toolTip = enableTooltip;
   this.enableCheckbox.onCheck = ( checked ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      if ( checked )
         this.referenceGroup.enableDrizzle();
      else
         this.referenceGroup.disableDrizzle();

      if ( this.onChange )
         this.onChange();
   };

   let enableSizer = new HorizontalSizer;
   enableSizer.spacing = 4;
   enableSizer.add( this.enableLabel );
   enableSizer.add( this.enableCheckbox );
   enableSizer.addStretch();

   //

   let fastTooltip = "<p>Select this option to compute the overlapping areas of each "
      + "drizzle droplet using LUTs (Look Up Tables).</p>"
      + "<p>Enabling LUTs significantly increases the execution speed at the price of "
      + "negligible error in the calculation of droplet overlapping areas. This option "
      + "is generally recommended.</p>";

   this.fastLabel = new Label( this );
   this.fastLabel.text = "Fast mode:";
   this.fastLabel.setFixedWidth( labelWidth );
   this.fastLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.fastLabel.toolTip = fastTooltip;

   this.fastCheckbox = new CheckBox( this );
   this.fastCheckbox.toolTip = fastTooltip;
   this.fastCheckbox.onCheck = ( checked ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleFast( checked );

      if ( this.onChange )
         this.onChange();
   };

   let fastSizer = new HorizontalSizer;
   fastSizer.spacing = 4;
   fastSizer.add( this.fastLabel );
   fastSizer.add( this.fastCheckbox );
   fastSizer.addStretch();

   if ( engine.fastMode )
   {
      this.fastLabel.visible = false;
      this.fastCheckbox.visible = false;
   }


   //

   let scaleTooltip = "<p>Drizzle output scale, or <i>subsampling ratio</i>. This is the factor that "
      + "multiplies input image dimensions (width, height) to compute the dimensions in pixels of the output integrated "
      + "image. For example, to perform a 'drizzle x2' integration, the corresponding drizzle scale is 2 and the output "
      + "image will have four times the area of the input reference image in square pixels.</p>";

   this.scaleLabel = new Label( this );
   this.scaleLabel.text = "Scale:";
   this.scaleLabel.setFixedWidth( labelWidth );
   this.scaleLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.scaleLabel.toolTip = scaleTooltip;

   this.scaleSpinBox = new SpinBox( this );
   this.scaleSpinBox.minValue = 1;
   this.scaleSpinBox.maxValue = 4;
   this.scaleSpinBox.toolTip = scaleTooltip;
   this.scaleSpinBox.onValueUpdated = ( value ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleScale( value );
      if ( this.onChange )
         this.onChange();
   };

   let scaleSizer = new HorizontalSizer;
   scaleSizer.spacing = 4;
   scaleSizer.add( this.scaleLabel );
   scaleSizer.add( this.scaleSpinBox );
   scaleSizer.addStretch();

   //

   let dropShrinkTooltip = "<p>Drizzle drop shrink factor. This is a reduction factor applied to input "
      + "image pixels. Smaller input pixels or <i>drops</i> tend to yield sharper results because the integrated image is "
      + "formed by convolution with a smaller PSF. However, smaller input pixels are more prone to <i>dry</i> (uncovered) "
      + "output pixels, visible patterns caused by partial sampling, and overall decreased SNR. Low shrink factors require "
      + "more and better dithered input images. The default drop shrink factor is 0.9.</p>";

   this.dropShrinkNumericControl = new NumericControl( this );
   this.dropShrinkNumericControl.label.text = "Drop shrink:";
   this.dropShrinkNumericControl.label.setFixedWidth( labelWidth );
   this.dropShrinkNumericControl.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.dropShrinkNumericControl.label.toolTip = dropShrinkTooltip;

   this.dropShrinkNumericControl.setRange( 0, 1 );
   this.dropShrinkNumericControl.slider.setRange( 0, 100 );
   this.dropShrinkNumericControl.setPrecision( 2 );
   this.dropShrinkNumericControl.toolTip = dropShrinkTooltip;
   this.dropShrinkNumericControl.onValueUpdated = ( value ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleDropShrink( value );
      if ( this.onChange )
         this.onChange();
   };

   //

   let functionTooltip = "<p>Drizzle drop kernel function. This parameter defines the shape of an input "
      + "drop as a two-dimensional surface function. Square and circular kernels are applied by computing the area of the "
      + "intersection between each drop and the projected output pixel. Gaussian and variable shape kernels are applied by "
      + "computing the double integral of the surface function over the intersection between the drop and the projected output "
      + "pixel on the XY plane. Square kernels are used by default.</p>"
      + "<p>Gaussian and variable shape drizzle kernels (the latter providing finer control on function profiles) can be used "
      + "to improve resolution of the integrated image. However, these functions tend to require much more and much better "
      + "dithered data than the standard square and circular kernels to achieve optimal results.</p>";

   this.functionLabel = new Label( this );
   this.functionLabel.text = "Function:";
   this.functionLabel.setFixedWidth( labelWidth );
   this.functionLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.functionLabel.toolTip = functionTooltip;

   let kernels = [
      "Square",
      "Circular",
      "Gaussian",
      "VarShape, β = 1",
      "VarShape, β = 1.5",
      "VarShape, β = 3",
      "VarShape, β = 4",
      "VarShape, β = 5",
      "VarShape, β = 6"
   ];

   this.functionComboBox = new ComboBox( this );
   for ( let i = 0; i < kernels.length; ++i )
      this.functionComboBox.addItem( kernels[ i ] );
   this.functionComboBox.toolTip = functionTooltip;
   this.functionComboBox.onItemSelected = ( item ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleFunction( item );
      if ( this.onChange )
         this.onChange();
   };

   let functionSizer = new HorizontalSizer;
   functionSizer.spacing = 4;
   functionSizer.add( this.functionLabel );
   functionSizer.add( this.functionComboBox );
   functionSizer.addStretch();

   //

   let gridSizeTooltip = "<p>When Gaussian and variable shape drizzle kernel functions are used, this parameter defines "
      + "the number of discrete function values computed to approximate the double integral of the kernel surface function. More "
      + "function evaluations improve the accuracy of numerical integration at the cost of more computational work. The default "
      + "value of this parameter is 16, meaning that 16*16=256 function values are computed to integrate drizzle kernel functions.</p>";

   this.gridSizeLabel = new Label( this );
   this.gridSizeLabel.text = "Grid size:";
   this.gridSizeLabel.setFixedWidth( labelWidth );
   this.gridSizeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.gridSizeLabel.toolTip = gridSizeTooltip;

   this.gridSizeSpinBox = new SpinBox( this );
   this.gridSizeSpinBox.minValue = 4;
   this.gridSizeSpinBox.maxValue = 100;
   this.gridSizeSpinBox.toolTip = gridSizeTooltip;
   this.gridSizeSpinBox.onValueUpdated = ( value ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleGridSize( value );
      if ( this.onChange )
         this.onChange();
   };

   let gridSizeSizer = new HorizontalSizer;
   gridSizeSizer.spacing = 4;
   gridSizeSizer.add( this.gridSizeLabel );
   gridSizeSizer.add( this.gridSizeSpinBox );
   gridSizeSizer.addStretch();

   //

   let dummyLabel = new Label( this );
   dummyLabel.setFixedWidth( labelWidth );

   this.setDefaultsButton = new PushButton( this );
   this.setDefaultsButton.text = "Reset";
   this.setDefaultsButton.toolTip = "<p>Resets drizzle integration parameters for the selected group.</p>"
      + "<p>The default drizzle scale is <b>1x</b>.<br/>"
      + "The default drop shrink is <b>0.9</b> for grayscale images, <b>1.0</b> for CFA images.<br/>"
      + "The default kernel function is <b>square</b>.</p>";
   this.setDefaultsButton.onClick = () =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.setDrizzleDataDefaults();
      if ( this.onChange )
         this.onChange();
   };

   let defaultsSizer = new HorizontalSizer;
   defaultsSizer.spacing = 4;
   defaultsSizer.add( dummyLabel );
   defaultsSizer.add( this.setDefaultsButton );

   //

   this.applyToAllGroupsButton = new PushButton( this );
   this.applyToAllGroupsButton.text = "Apply to all groups";
   this.applyToAllGroupsButton.toolTip = "<p>Apply the current settings to all post calibration groups.</p>";
   this.applyToAllGroupsButton.onClick = () =>
   {
      if ( this.referenceGroup == undefined )
         return;

      engine.parametersManager.applyDrizzleConfiguration( this.referenceGroup );
      if ( this.onChange )
         this.onChange();
   };

   //

   // layout
   this.add( enableSizer );
   this.add( fastSizer );
   this.add( scaleSizer );
   this.add( this.dropShrinkNumericControl );
   this.add( functionSizer );
   this.add( gridSizeSizer );
   this.add( defaultsSizer );
   this.add( this.applyToAllGroupsButton );

   this.updateWithGroup = ( group ) =>
   {
      if ( group )
         this.referenceGroup = group;
      // store the reference group if provided
      if ( this.referenceGroup == undefined )
         return;

      this.enableCheckbox.checked = this.referenceGroup.isDrizzleEnabled();
      this.fastCheckbox.checked = this.referenceGroup.drizzleFast();
      this.scaleSpinBox.value = this.referenceGroup.drizzleScale();
      this.dropShrinkNumericControl.setValue( this.referenceGroup.drizzleDropShrink() );
      this.functionComboBox.currentItem = this.referenceGroup.drizzleFunction();
      this.gridSizeSpinBox.value = this.referenceGroup.drizzleGridSize();

      let controlsEnabled = this.enableCheckbox.checked && this.referenceGroup.isDrizzleAvailable();

      this.enableCheckbox.enabled = group.isDrizzleAvailable();
      this.fastCheckbox.enabled = controlsEnabled;
      this.scaleSpinBox.enabled = controlsEnabled;
      this.dropShrinkNumericControl.enabled = controlsEnabled;
      this.functionComboBox.enabled = controlsEnabled;
      this.gridSizeSpinBox.enabled = controlsEnabled;
      this.setDefaultsButton.enabled = controlsEnabled;

      // grid size is enabled for Gaussian and VarShape only
      this.gridSizeSpinBox.enabled = this.gridSizeSpinBox.enabled && ( this.referenceGroup.getDrizzleGridSizeString().length > 0 );
   };

   this.update();
   }
}

/**
 * Controls that shows the Fast Integration configurations for a post-process group
 *
 * @param {*} parent
 */
var FastIntegrationConfiguration = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Fast Integration", parent );

   let labelWidth = this.font.width( "MMMMMMMM: " );

   //

   // the enable checkbox is not created in fastMode since FastIntegration is always active
   let enableSizer;
   if ( !engine.fastMode )
   {
      let enableTooltip = "<p>Enables the fast integration process for the selected group.</p>";

      this.enableLabel = new Label( this );
      this.enableLabel.text = "Enable:";
      this.enableLabel.setFixedWidth( labelWidth );
      this.enableLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
      this.enableLabel.toolTip = enableTooltip;

      this.enableCheckbox = new CheckBox( this );
      this.enableCheckbox.toolTip = enableTooltip;
      this.enableCheckbox.onCheck = ( checked ) =>
      {
         if ( this.referenceGroup == undefined )
            return;
         this.referenceGroup.enableFastIntegration( checked, true /* manually changed */ );
         if ( this.onChange )
            this.onChange();
      }

      enableSizer = new HorizontalSizer;
      enableSizer.spacing = 4;
      enableSizer.add( this.enableLabel );
      enableSizer.add( this.enableCheckbox );
      enableSizer.addStretch();
   }

   //

   let saveImagesTooltip = "<p>Enables the generation of registered images.</p>"
      + "<p>FastIntegration is an in-memory process that reads, aligns, normalize, and integrate images to "
      + "generate a master light without the need of writing intermediate results as disk files.</p>"
      + "<p>Enable this checkbox to save the registered files to disk for further inspection if required.</p>";

   this.saveImagesLabel = new Label( this );
   this.saveImagesLabel.text = "Save images:";
   this.saveImagesLabel.setFixedWidth( labelWidth );
   this.saveImagesLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.saveImagesLabel.toolTip = saveImagesTooltip;

   this.saveImagesCheckbox = new CheckBox( this );
   this.saveImagesCheckbox.toolTip = saveImagesTooltip;
   this.saveImagesCheckbox.onCheck = ( checked ) =>
   {
      if ( this.referenceGroup == undefined )
         return;
      this.referenceGroup.enableFastIntegrationImageSaving( checked );
      if ( this.onChange )
         this.onChange();
   }

   let saveSizer = new HorizontalSizer;
   saveSizer.spacing = 4;
   saveSizer.add( this.saveImagesLabel );
   saveSizer.add( this.saveImagesCheckbox );
   saveSizer.addStretch();

   //

   let weightingTooltip = "<p>Enables fast image quality measurements and the generation of weights assigned "
      + "to integrated frames.</p>"
      + "<p><b>Resolution</b> favors images with stars that have a higher spatial flux concentration. This criterion "
      + "assigns higher weights to images with higher signal and sharpener stars, and penalizes images poorly guided, "
      + "defocused, or covered by clouds or affected by worse atmospheric transparency conditions.</p>"
      + "<p><b>PSF SNR</b> promotes images with higher SNR, measured in terms of the ratio between the star flux and "
      + "the noise of the area surrounding each measured star.</p>";

   this.weightingLabel = new Label( this );
   this.weightingLabel.text = "Weighting:";
   this.weightingLabel.setFixedWidth( labelWidth );
   this.weightingLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.weightingLabel.toolTip = weightingTooltip;

   this.weightingComboBox = new ComboBox( this );
   this.weightingComboBox.toolTip = weightingTooltip;
   this.weightingComboBox.addItem( "None" );
   this.weightingComboBox.addItem( "PSF SNR" );
   this.weightingComboBox.addItem( "Resolution" );
   this.weightingComboBox.onItemSelected = ( item ) =>
   {
      if ( this.referenceGroup == undefined )
         return;

      this.referenceGroup.enableFastIntegrationWeightingScheme( item );
      if ( this.onChange )
         this.onChange();
   }

   let weightingSizer = new HorizontalSizer;
   weightingSizer.spacing = 4;
   weightingSizer.add( this.weightingLabel );
   weightingSizer.add( this.weightingComboBox );

   this.applyToAllGroupsButton = new PushButton( this );
   this.applyToAllGroupsButton.text = "Apply to all groups";
   this.applyToAllGroupsButton.toolTip = "<p>Apply the current settings to all post calibration groups.</p>";
   this.applyToAllGroupsButton.onClick = () =>
   {
      if ( this.referenceGroup == undefined )
         return;

      engine.parametersManager.applyFastIntegrationConfiguration( this.referenceGroup );
      if ( this.onChange )
         this.onChange();
   }


   // CONTINUE IMPLEMENTING THE WEIGHTING OPTION

   // layout
   if ( !engine.fastMode )
      this.add( enableSizer );
   this.add( saveSizer );
   this.add( weightingSizer );
   this.add( this.applyToAllGroupsButton );

   this.updateWithGroup = ( group ) =>
   {
      //  this control is incompatible with any associated channel
      this.enabled = !group.isVirtual();
      if ( group )
         this.referenceGroup = group;
      // store the reference group if provided
      if ( this.referenceGroup == undefined )
         return;

      if ( !engine.fastMode )
         this.enableCheckbox.checked = this.referenceGroup.fastIntegrationData.enabled;
      this.saveImagesCheckbox.checked = this.referenceGroup.fastIntegrationData.saveRegisteredImages;
      this.weightingComboBox.currentItem = this.referenceGroup.fastIntegrationData.weightingScheme;
   }

   }
}


/**
 * Controls that shows the status of the post processing steps
 *
 * @param {*} parent
 */
var PostProcessingSteps = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Active Steps", parent );

   // Linear Pattern Subtraction
   this.isLPSEnabled = new CheckBox( this );
   this.isLPSEnabled.text = "Linear Defects Correction";
   this.isLPSEnabled.toolTip = "<p>When checked, Linear Defects Correction will be performed.</p>";
   this.isLPSEnabled.onCheck = ( checked ) =>
   {
      engine.linearPatternSubtraction = checked;
      this.parent.parent.dialog.updateControls();
   };

   // Image weighting
   this.isSubframeWeightingEnabled = new CheckBox( this );
   this.isSubframeWeightingEnabled.text = "Subframe Weighting";
   this.isSubframeWeightingEnabled.toolTip = "<p>When checked, weights will be computed and stored into the light frames metadata.</p>";
   this.isSubframeWeightingEnabled.onCheck = ( checked ) =>
   {
      engine.subframeWeightingEnabled = checked;
      this.parent.parent.dialog.updateControls();
   };

   // Image Registration
   this.isImageRegistrationEnabled = new CheckBox( this );
   this.isImageRegistrationEnabled.text = "Image Registration";
   this.isImageRegistrationEnabled.toolTip = "<p>When checked, light frames star alignment will be performed.</p>";
   this.isImageRegistrationEnabled.onCheck = ( checked ) =>
   {
      engine.imageRegistration = checked;
      this.parent.parent.dialog.updateControls();
   };

   // Local Normalization
   this.isLocalNormalizationEnabled = new CheckBox( this );
   this.isLocalNormalizationEnabled.text = "Local Normalization";
   this.isLocalNormalizationEnabled.toolTip = "<p>When checked, local normalization will be used as the image normalization method.</p>";
   this.isLocalNormalizationEnabled.onCheck = ( checked ) =>
   {
      engine.localNormalization = checked;
      this.parent.parent.dialog.updateControls();
   };

   // Image Integration
   this.isImageIntegrationEnabled = new CheckBox( this );
   this.isImageIntegrationEnabled.text = "Image Integration";
   this.isImageIntegrationEnabled.toolTip = "<p>When checked, master light frames will be generated.</p>";
   this.isImageIntegrationEnabled.onCheck = ( checked ) =>
   {
      engine.integrate = checked;
      this.parent.parent.dialog.updateControls();
   };

   // layout
   this.add( this.isLPSEnabled );
   this.add( this.isSubframeWeightingEnabled );
   this.add( this.isImageRegistrationEnabled );
   this.add( this.isLocalNormalizationEnabled );
   this.add( this.isImageIntegrationEnabled );

   this.updateContent = () =>
   {
      let makeBold = ( comp ) =>
      {
         let font = comp.font;
         font.bold = comp.checked;
         comp.font = font;
      };

      this.isLPSEnabled.checked = engine.linearPatternSubtraction;
      makeBold( this.isLPSEnabled );
      this.isSubframeWeightingEnabled.checked = engine.subframeWeightingEnabled;
      makeBold( this.isSubframeWeightingEnabled );
      this.isImageRegistrationEnabled.checked = engine.imageRegistration;
      makeBold( this.isImageRegistrationEnabled );
      this.isLocalNormalizationEnabled.checked = engine.localNormalization;
      makeBold( this.isLocalNormalizationEnabled );
      this.isImageIntegrationEnabled.checked = engine.integrate;
      makeBold( this.isImageIntegrationEnabled );
   };

   this.updateContent();
   }
}

// ----------------------------------------------------------------------------

var EventScriptControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Event Script", parent, false /* expand */ , true /* deactivatable */ );

   //

   this.onActivateStatusChanged = ( checked ) =>
   {
      engine.usePipelineScript = checked;
      this.updateContent();
   };

   //

   this.scriptFileEdit = new Edit( this );
   this.scriptFileEdit.setVariableWidth();

   this.scriptFileSelectButton = new ToolButton( this );
   this.scriptFileSelectButton.icon = this.scaledResource( ":/icons/select-file.png" );
   this.scriptFileSelectButton.setScaledFixedSize( 20, 20 );
   this.scriptFileSelectButton.toolTip = "<p>Select the event script file.</p>";
   this.scriptFileSelectButton.onClick = () =>
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = false;
      ofd.caption = "Select WBPP Event Script";
      ofd.filters = [
         [ "JavaScript files", ".js" ]
      ];
      if ( ofd.execute() )
         this.scriptFileEdit.text = engine.pipelineScriptFile = ofd.filePath;
   };

   this.updateContent = () =>
   {
      this.scriptFileEdit.text = engine.pipelineScriptFile;
      if ( engine.usePipelineScript )
         this.activate();
      else
         this.deactivate();
   };

   let sizer = new HorizontalSizer;
   sizer.spacing = 4;
   sizer.add( this.scriptFileEdit );
   sizer.add( this.scriptFileSelectButton );

   this.add( sizer );
   }
}

// ----------------------------------------------------------------------------

var PipelineBuilderScriptControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Pipeline builder", parent, false /* expand */ , true /* deactivatable */ );

   //

   this.onActivateStatusChanged = ( checked ) =>
   {
      engine.usePipelineBuilderScript = checked;
      this.dialog.updateControls();
   };

   //

   let toolTip = "<p>Assign a pipeline builder script to customize the WBPP pipeline.</p>"
      + "<p>The pipeline builder, if assigned, is responsible for building the "
      + "pipeline for the light frames only. WBPP remains responsible for the bias, "
      + "dark and flat frames, and the generation of the corresponding master files.</p>"
      + "<p>In case of error, the default pipeline will be used as a fallback.</p>";

   this.scriptFileEdit = new Edit( this );
   this.scriptFileEdit.setVariableWidth();
   this.scriptFileEdit.toolTip = toolTip;
   this.scriptFileEdit.onLoseFocus = () =>
   {
      if ( engine.pipelineBuilderScriptFile != this.scriptFileEdit.text )
      {
         engine.pipelineBuilderScriptFile = this.scriptFileEdit.text;
         this.dialog.updateControls();
      }
   };

   this.scriptFileSelectButton = new ToolButton( this );
   this.scriptFileSelectButton.icon = this.scaledResource( ":/icons/select-file.png" );
   this.scriptFileSelectButton.setScaledFixedSize( 20, 20 );
   this.scriptFileSelectButton.toolTip = toolTip;
   this.scriptFileSelectButton.onClick = () =>
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = false;
      ofd.caption = "Select WBPP Pipeline Builder Script";
      ofd.filters = [
         [ "JavaScript files", ".js" ]
      ];
      if ( ofd.execute() )
      {
         this.scriptFileEdit.text = engine.pipelineBuilderScriptFile = ofd.filePath;
         this.dialog.updateControls();
      }
   };

   this.updateContent = () =>
   {
      this.scriptFileEdit.text = engine.pipelineBuilderScriptFile;
      if ( engine.usePipelineBuilderScript )
      {
         this.activate();
         this.error.text = engine.pipelineBuilderError;
         this.error.visible = engine.pipelineBuilderError != "";
      }
      else
      {
         this.deactivate();
         this.error.visible = false;
      }
   };

   let sizer = new HorizontalSizer;
   sizer.spacing = 4;
   sizer.add( this.scriptFileEdit );
   sizer.add( this.scriptFileSelectButton );

   this.error = new Label( this );
   this.error.text = "";
   this.error.useRichText = true;
   this.error.styleSheet = "QLabel { color: red; }";

   this.add( sizer );
   this.add( this.error );
   }
}

// ----------------------------------------------------------------------------

var PipelinePanel = class extends Control
{
   constructor( parent )
   {
      super( parent );

   // we use the same control panel treebox style
   this.treeBox = WBPPUtils.factory.CPTreeBox( parent );

   this.setHeaders = () =>
   {
      this.treeBox.numberOfColumns = 4;
      this.treeBox.setHeaderText( 0, "#" );
      this.treeBox.setHeaderText( 1, "Operation" );
      this.treeBox.setHeaderText( 2, "Group details" );
      this.treeBox.setHeaderText( 3, "Est. disk space" );
      this.treeBox.setHeaderAlignment( 3, TextAlignment.VertCenter | TextAlignment.Right );
      this.treeBox.setHeaderText( 4, "" );
   };

   /**
    * Refreshes the content with the updates status.
    *
    */
   this.updateContent = () =>
   {
      // filter the logged operations and populate the tree box
      this.treeBox.clear();

      let trackableOperations = engine.operationQueue.trackableOperations();
      for ( let i = 0; i < trackableOperations.length; ++i )
      {
         let operation = trackableOperations[ i ];
         operation.updateGroupDescription( false, true )

         let node = new TreeBoxNode();
         node.setText( 0, "" + i );
         node.setText( 1, operation.name );
         node.setText( 2, operation.groupDescription );
         let space = operation.spaceRequired()
         if ( space == 0 )
            node.setText( 3, " - " );
         else
            node.setText( 3, WBPPUtils.readableSize( operation.spaceRequired() ) );
         node.setAlignment( 3, TextAlignment.Right );

         this.treeBox.add( node );
      }

      this.treeBox.adjustColumnWidthToContents( 0 );
      this.treeBox.adjustColumnWidthToContents( 1 );
      this.treeBox.adjustColumnWidthToContents( 2 );
      this.treeBox.adjustColumnWidthToContents( 3 );

      this.postProcessStatus.updateContent();
      this.pipelineScript.updateContent();
      this.pipelineBuilderScript.updateContent();
   };

   this.setHeaders();

   //

   this.optionsPanelWidth = parent.logicalPixelsToPhysical( 240 );

   // the right side controls container
   this.rightContainer = new Control( this );
   this.rightContainer.sizer = new VerticalSizer;
   this.rightContainer.sizer.spacing = 4;
   if ( !engine.fastMode )
      this.rightContainer.setFixedWidth( this.optionsPanelWidth );

   // show the post process steps
   this.postProcessStatus = new PostProcessingSteps( this.rightContainer );
   this.postProcessStatus.setFixedWidth( this.optionsPanelWidth );
   this.postProcessStatus.visible = !engine.fastMode;

   // show the pipeline script editor
   this.pipelineScript = new EventScriptControl( this.rightContainer );
   this.pipelineScript.setActivatableCheckboxTooltip( "<p>Enable or disable the event script.</p>" )
   this.pipelineScript.setFixedWidth( this.optionsPanelWidth );
   this.pipelineScript.visible = !engine.fastMode;

   // show the pipeline script editor
   this.pipelineBuilderScript = new PipelineBuilderScriptControl( this.rightContainer );
   this.pipelineBuilderScript.setActivatableCheckboxTooltip( "<p>Enable or disable the pipeline builder script.</p>" )
   this.pipelineBuilderScript.setFixedWidth( this.optionsPanelWidth );
   this.pipelineBuilderScript.visible = !engine.fastMode;

   this.rightContainer.sizer.add( this.postProcessStatus );
   this.rightContainer.sizer.add( this.pipelineScript );
   this.rightContainer.sizer.add( this.pipelineBuilderScript );
   this.rightContainer.sizer.addStretch();

   //

   this.sizer = new HorizontalSizer;
   this.sizer.margin = 4;
   this.sizer.spacing = 4;
   this.sizer.add( this.treeBox );
   this.sizer.add( this.rightContainer );
   }
}

// ----------------------------------------------------------------------------
/**
 * Main TAB view containing the list of bias/dark/flat/light tree boxes and the
 * group options / calibration diagram button on the right side.
 */
var CalibrationPanel = class extends Control
{
   constructor( parent )
   {
      super( parent );

   // styles
   this.defaultFontColor = 0xFF000000;
   this.calibratedByColor = 0xFF333333;
   this.calibratesColorAuto = 0xFF55AA55;
   this.calibratesColorManual = 0xFF154C99;
   this.disabledColor = 0x88BBBBBB;
   this.fontSize = 8;
   this.optionsPanelWidth = parent.logicalPixelsToPhysical( 240 );

   // global maps of the group.id with the note in the tree boxes
   this.groupNodeMap = {};
   this.selectedGroup = undefined;
   this.selectedNode = undefined;

   // active calibration groups
   this.graphCalibrationBias = null;
   this.graphCalibrationDark = null;
   this.graphCalibrationFlat = null;
   this.graphCalibrationLight = null;

   // tree box descriptors
   this.biasDescriptor = new GroupTreeBoxDescriptor( ImageType.Bias );
   this.darkDescriptor = new GroupTreeBoxDescriptor( ImageType.Dark );
   this.flatDescriptor = new GroupTreeBoxDescriptor( ImageType.Flat );
   this.lightDescriptor = new GroupTreeBoxDescriptor( ImageType.Light );

   // ---
   // GUI
   // ---

   // create duplicated treeboxes to implement page flipping.
   // When update() in invoked, we switch treeboxes and update the hidden ones; once the update
   // is ready we make them visible and hide the old.
   this.biasTreeBoxes = [ WBPPUtils.factory.CPTreeBox( parent ), WBPPUtils.factory.CPTreeBox( parent ) ];
   this.darkTreeBoxes = [ WBPPUtils.factory.CPTreeBox( parent ), WBPPUtils.factory.CPTreeBox( parent ) ];
   this.flatTreeBoxes = [ WBPPUtils.factory.CPTreeBox( parent ), WBPPUtils.factory.CPTreeBox( parent ) ];
   this.lightTreeBoxes = [ WBPPUtils.factory.CPTreeBox( parent ), WBPPUtils.factory.CPTreeBox( parent ) ];

   // the current page index, indicating which treeboxes are currently active.
   // The active trees are the ones used by all functions, they are not necessarily visible.
   this.treesPageIndex = 0;

   /**
    * Makes the active treeboxes visible.
    * This function is invoked when the update is completed and the new treeboxes are ready
    * to be presented.
    */
   this._makeActiveTreesVisible = () =>
   {
      for ( let i = 0; i < 2; ++i )
      {
         this.biasTreeBoxes[ i ].visible = this.treesPageIndex == i;
         this.darkTreeBoxes[ i ].visible = this.treesPageIndex == i;
         this.flatTreeBoxes[ i ].visible = this.treesPageIndex == i;
         this.lightTreeBoxes[ i ].visible = this.treesPageIndex == i;
      }
   };

   /**
    * This function swaps the active treeboxes. Before proceeding with an update, the treeboxes
    * should be swapped in order to make active the hidden ones and perform the updates off-screen.
    */
   this._swapActiveTrees = () =>
   {
      this.treesPageIndex = this.treesPageIndex == 0 ? 1 : 0;
      this.biasTreeBox = this.biasTreeBoxes[ this.treesPageIndex ];
      this.darkTreeBox = this.darkTreeBoxes[ this.treesPageIndex ];
      this.flatTreeBox = this.flatTreeBoxes[ this.treesPageIndex ];
      this.lightTreeBox = this.lightTreeBoxes[ this.treesPageIndex ];
      this.treeBoxes = [ this.biasTreeBox, this.darkTreeBox, this.flatTreeBox, this.lightTreeBox ];
   };

   // set the active tree boxes
   this._swapActiveTrees();

   // Tree Box sizer
   let treeBoxesSizer = new VerticalSizer;
   treeBoxesSizer.spacing = 4;

   // we add all treeboxes, during the update we make visible only the updated ones once the udpate is completed.
   for ( let i = 0; i < 2; ++i )
   {
      treeBoxesSizer.add( this.biasTreeBoxes[ i ] );
      treeBoxesSizer.add( this.darkTreeBoxes[ i ] );
      treeBoxesSizer.add( this.flatTreeBoxes[ i ] );
      treeBoxesSizer.add( this.lightTreeBoxes[ i ] );
   }

   /**
    * Logic to be performed when a new row is highlighted in a treebox.
    *
    * @param {*} treeBox the treebox that contains the selected row
    * @return {*}
    */
   this._treeBoxRowSelectionUpdated = ( treeBox ) =>
   {
      // record that the selection has been changed
      this.selectionWasUpdated = true;
      // reset all tree boxes to their default appearance
      this._resetTableAppearance( this.disabledColor );
      // search for the selected node and retrieve the group
      if ( treeBox.selectedNodes.length == 0 )
      {
         this._unselectAllNodesExcept();
         this._updateTreeBoxNodeContents();
         this._updateStatusBox();
         this._updateShowGraphButton();
         return undefined;
      }
      // save the currently selected node and group
      this.selectedNode = treeBox.selectedNodes[ 0 ];
      this.selectedGroup = this.selectedNode.__group__;

      // get the selected node on the current treeBox
      let nodeFont = this.selectedNode.font( 1 );
      nodeFont.bold = true;
      let nodeColor = this.selectedNode.textColor( 1 );
      this._setNodeFontBold( this.selectedNode, true );
      this._setNodeFontColor( this.selectedNode, nodeColor );
      // unselect all nodes in all treeBoxes except the currently selected one
      this._unselectAllNodesExcept( this.selectedNode );
      // get the array of groups that are calibrated by this group and
      // highlight the rows corresponding to the calibrated groups
      engine.calibrationMatcher.getGroupsCalibratedBy( this.selectedGroup ).forEach( cg =>
      {
         let n = this.groupNodeMap[ cg.id ];
         this._setNodeFontBold( n, true );
         this._setNodeFontColor( n, this.calibratedByColor );
      } );

      // initialize the current graph groups
      this.graphCalibrationBias = null;
      this.graphCalibrationDark = null;
      this.graphCalibrationFlat = null;
      this.graphCalibrationLight = this.selectedGroup.isMaster ? null : this.selectedGroup;
      // get the array of groups that calibrates the selected group
      let calibGroups = this.selectedGroup.isMaster
         ?
         {} : engine.calibrationMatcher.getCalibrationGroupsFor( this.selectedGroup );
      Object.keys( calibGroups ).forEach( key =>
      {
         if ( calibGroups[ key ] )
         {
            let cg = calibGroups[ key ];
            let n = this.groupNodeMap[ cg.id ];
            this._setNodeFontBold( n, true );
            if ( ( this.selectedGroup.overrideDark && this.selectedGroup.overrideDark.id == cg.id )
               || ( this.selectedGroup.overrideFlat && this.selectedGroup.overrideFlat.id == cg.id ) )
            {
               this._setNodeFontColor( n, this.calibratesColorManual );
            }
            else
            {
               this._setNodeFontColor( n, this.calibratesColorAuto );
            }
            // prepare the current calibration files
            if ( !this.selectedGroup.isMaster )
               switch ( cg.imageType )
               {
                  case ImageType.Bias:
                     this.graphCalibrationBias = cg;
                     break;
                  case ImageType.Dark:
                     this.graphCalibrationDark = cg;
                     break;
                  case ImageType.Flat:
                     this.graphCalibrationFlat = cg;
                     break;
               }
         }
      } );
      // update all nodes content
      this._updateTreeBoxNodeContents();
      // update the show status box
      this._updateStatusBox();
      // enable edit group and show graph button
      this._updateShowGraphButton();
      // show the controls for the selected group
      this.overscanSettingsControl.updateWithGroup( this.selectedGroup );
      this.calibrationSettingsControl.updateWithGroup( this.selectedGroup );
      this.pedestalSettingsControl.updateWithGroup( this.selectedGroup );
      this.cosmeticCorrectionSettingsControl.updateWithGroup( this.selectedGroup );
      this.debayerSettingsControl.updateWithGroup( this.selectedGroup );
      return undefined;
   };

   /**
    * Logic called when a node is clicked.
    * In the current implementation, this function is called after
    * "_treeBoxRowSelectionUpdated" when a new node is selected, and
    * is called alone when a selected node is clicked.
    * This completes the lifecycle of manual node selection manages
    * the case where we click on an already selected group
    * to disable it.
    *
    * @return {*}
    */
   this._onNodeClicked = () =>
   {
      if ( !this.selectionWasUpdated )
      {
         this._resetTableAppearance( this.defaultFontColor );
         this._unselectAllNodesExcept();
         this.graphCalibrationBias = null;
         this.graphCalibrationDark = null;
         this.graphCalibrationFlat = null;
         this.graphCalibrationLight = null;
         this.overscanSettingsControl.hideControls();
         this.calibrationSettingsControl.hideControls();
         this.pedestalSettingsControl.hideControls();
         this.cosmeticCorrectionSettingsControl.hideControls();
         this.debayerSettingsControl.hideControls();
      }
      this.selectionWasUpdated = false;
      this._updateShowGraphButton();
      return undefined;
   };

   /**
    * This function updates the status box message showing warnings or errors,
    * accordingly to the currently selected group.
    *
    */
   this._updateStatusBox = () =>
   {
      // show the status if needed
      let status = this.selectedGroup ? this.selectedGroup.status()
         :
         {};
      this.statusTextBox.visible = ( status.errors || status.warnings ) != undefined;
      this.statusTextBox.text = "<b><u>" + ( status.errors ? "ERRORS" : "WARNINGS" ) + "</u></b><br><br>" + ( status.errors || status.warnings || "" );
      this.statusTextBox.foregroundColor = status.errors ? 0xFFFF0000 : 0xFF333333;
      this.statusTextBox.home();
   };

   /**
    * This function refreshes all treeboxes nodes with the corresponding group data.
    *
    */
   this._updateTreeBoxNodeContents = () =>
   {
      // update all nodes content
      engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE ).forEach( group =>
      {
         let node = this.groupNodeMap[ group.id ];
         if ( node )
            this._fillGroupRowData( group, node );
      } );
   };

   /**
    * Configures all treebox headers.
    *
    */
   this._setColumnHeaders = () =>
   {
      // the calibration mode
      let mode = BPP.GroupingMode.PRE;

      [
      {
         treeBox: this.biasTreeBox,
         descriptor: this.biasDescriptor
      },
      {
         treeBox: this.darkTreeBox,
         descriptor: this.darkDescriptor
      },
      {
         treeBox: this.flatTreeBox,
         descriptor: this.flatDescriptor
      },
      {
         treeBox: this.lightTreeBox,
         descriptor: this.lightDescriptor
      } ].forEach( obj =>
      {
         let headers = obj.descriptor.headers( BPP.GroupingMode.PRE );

         obj.treeBox.numberOfColumns = headers.length;
         for ( let i = 0; i < headers.length; ++i )
         {
            obj.treeBox.setHeaderAlignment( i, TextAlignment.Center );
            if ( headers[ i ] )
               obj.treeBox.setHeaderText( i, headers[ i ] );
            else
               obj.treeBox.setHeaderText( i, "" );
         }
      } );

      let keywordsForMode = engine.keywords.keywordsForMode( mode );
      let nKeywords = keywordsForMode.length;
      let biasBaseColumns = this.biasDescriptor.headers( mode ).length;
      this.biasTreeBox.numberOfColumns = biasBaseColumns + nKeywords + 1;
      let darkBaseColumns = this.darkDescriptor.headers( mode ).length;
      this.darkTreeBox.numberOfColumns = darkBaseColumns + nKeywords + 1;
      let flatBaseColumns = this.flatDescriptor.headers( mode ).length;
      this.flatTreeBox.numberOfColumns = flatBaseColumns + nKeywords + 1;
      let lightBaseColumns = this.lightDescriptor.headers( mode ).length;
      this.lightTreeBox.numberOfColumns = lightBaseColumns + nKeywords + 1;

      keywordsForMode.forEach( ( kw, i ) =>
      {
         this.biasTreeBox.setHeaderText( biasBaseColumns + i, kw.name );
         this.biasTreeBox.setHeaderAlignment( biasBaseColumns + i, TextAlignment.Center );

         this.darkTreeBox.setHeaderText( darkBaseColumns + i, kw.name );
         this.darkTreeBox.setHeaderAlignment( darkBaseColumns + i, TextAlignment.Center );

         this.flatTreeBox.setHeaderText( flatBaseColumns + i, kw.name );
         this.flatTreeBox.setHeaderAlignment( flatBaseColumns + i, TextAlignment.Center );

         this.lightTreeBox.setHeaderText( lightBaseColumns + i, kw.name );
         this.lightTreeBox.setHeaderAlignment( lightBaseColumns + i, TextAlignment.Center );
      } );

      // remove the header title from the last column
      this.biasTreeBox.setHeaderText( biasBaseColumns + nKeywords, "" );
      this.darkTreeBox.setHeaderText( darkBaseColumns + nKeywords, "" );
      this.flatTreeBox.setHeaderText( flatBaseColumns + nKeywords, "" );
      this.lightTreeBox.setHeaderText( lightBaseColumns + nKeywords, "" );
   };


   /**
    * Enables or disables the graph button depending on the selected group type.
    *
    */
   this._updateShowGraphButton = () =>
   {
      this.showGraphButton.enabled =
         this.selectedGroup != undefined
         && ( [ ImageType.Bias, ImageType.Dark ].indexOf( this.selectedGroup.imageType ) == -1 );
   };

   // stores the state of the selection to support the logic of select/unselect an item by
   // clicking it multiple times
   this.selectionWasUpdated = false;

   // set the treeBox event handlers for all treeBoxes
   [ this.biasTreeBoxes, this.darkTreeBoxes, this.flatTreeBoxes, this.lightTreeBoxes ].forEach( treeBoxes =>
   {
      treeBoxes.forEach( treeBox =>
      {
         treeBox.onNodeSelectionUpdated = () =>
         {
            this._treeBoxRowSelectionUpdated( treeBox );
         };
         treeBox.onNodeClicked = this._onNodeClicked;
      } );
   } );

   // the right side controls container
   this.rightContainer = new Control( this );
   this.rightContainer.setFixedWidth( this.optionsPanelWidth );

   // show controls
   this.overscanSettingsControl = new OverscanSettingsControl( this.rightContainer, this );
   this.overscanSettingsControl.setFixedWidth( this.optionsPanelWidth );
   this.overscanSettingsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGroupOverscanSettingsCollapsed = collapsed;
   };

   this.calibrationSettingsControl = new CalibrationSettingsControl( this.rightContainer, this );
   this.calibrationSettingsControl.setFixedWidth( this.optionsPanelWidth );
   this.calibrationSettingsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGroupCalibrationSettingsCollapsed = collapsed;
   };

   this.pedestalSettingsControl = new PedestalSettingsControl( this.rightContainer, this );
   this.pedestalSettingsControl.setFixedWidth( this.optionsPanelWidth );
   this.pedestalSettingsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGroupPedestalSettingsCollapsed = collapsed;
   };

   this.cosmeticCorrectionSettingsControl = new CosmeticCorrectionSettingsControl( this.rightContainer, this );
   this.cosmeticCorrectionSettingsControl.setFixedWidth( this.optionsPanelWidth );
   this.cosmeticCorrectionSettingsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGroupCCSettingsCollapsed = collapsed;
   };

   this.debayerSettingsControl = new DebayerSettingsControl( this.rightContainer, this );
   this.debayerSettingsControl.setFixedWidth( this.optionsPanelWidth );
   this.debayerSettingsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGroupDebayerSettingsCollapsed = collapsed;
   };

   // show calibration flow button
   this.showGraphButton = new PushButton( this.rightContainer );
   this.showGraphButton.text = "Show Calibration Diagram";
   this.showGraphButton.enabled = false;
   this.showGraphButton.onClick = () =>
   {
      // show a dialog depicting the calibration flow
      let calibrationFlowDialog = new CalibrationFlowDialog(
         this.graphCalibrationBias,
         this.graphCalibrationDark,
         this.graphCalibrationFlat,
         this.graphCalibrationLight,
         this.selectedGroup.optimizeMasterDark );
      calibrationFlowDialog.execute();
   };

   this.showGraphButtonSizer = new HorizontalSizer;
   this.showGraphButtonSizer.margin = 6;
   this.showGraphButtonSizer.add( this.showGraphButton );

   // the status textbox reporting the detected issues of the selected groups
   this.statusTextBox = new TextBox( this.rightContainer );
   this.statusTextBox.readOnly = true;
   this.statusTextBox.styleSheet = "pi--PixInsightConsole { "
      + "font-family: Hack, DejaVu Sans Mono, Monospace; font-size: 10pt; background: white; }";
   this.statusTextBox.setFixedWidth( this.optionsPanelWidth );
   this.statusTextBox.setMinHeight( 0 );

   // bottom sizer
   this.rightContainer.sizer = new VerticalSizer;
   let optionsSizer = this.rightContainer.sizer;
   optionsSizer.spacing = 4;
   optionsSizer.add( this.overscanSettingsControl );
   optionsSizer.add( this.calibrationSettingsControl );
   optionsSizer.add( this.pedestalSettingsControl );
   optionsSizer.add( this.cosmeticCorrectionSettingsControl );
   optionsSizer.add( this.debayerSettingsControl );
   optionsSizer.add( this.statusTextBox );
   optionsSizer.add( this.showGraphButtonSizer );
   optionsSizer.addStretch();

   if ( engine.fastMode )
   {
      this.pedestalSettingsControl.visible = false;
      this.pedestalSettingsControl.__alwaysHidden__ = true;
   }

   // layout elements
   this.sizer = new HorizontalSizer;
   this.sizer.margin = 4;
   this.sizer.spacing = 4;
   this.sizer.add( treeBoxesSizer );
   this.sizer.add( this.rightContainer );

   // -------------------
   // AUXILIARY FUNCTIONS
   // -------------------

   /**
    * Resets the font and the color or the treeboxes to default values.
    *
    * @param {*} defaultColor
    */
   this._resetTableAppearance = ( defaultColor ) =>
   {
      [ this.biasTreeBox, this.darkTreeBox, this.flatTreeBox, this.lightTreeBox ].forEach( treeBox =>
      {
         for ( let i = 0; i < treeBox.numberOfChildren; ++i )
         {
            // remove bold font from all table
            let node = treeBox.child( i );
            this._setNodeFontSize( node, this.fontSize );
            this._setNodeFontBold( node, false );
            this._setNodeFontColor( node, defaultColor );

            let group = node.__group__;

            // if group is master than emphasize the column with the group name
            if ( group.hasMaster )
            {
               let font = node.font( 1 );
               font.bold = true;
               node.setFont( 1, font );
            }
         }
      } );

      // hide the status box
      this.statusTextBox.visible = false;
   };

   /**
    * Sets the font size of all cells of a node.
    *
    * @param {*} node the node to handle
    * @param {*} size the font size to set
    * @return {*}
    */
   this._setNodeFontSize = ( node, size ) =>
   {
      if ( !node.parentTree )
         return;
      for ( let j = 0; j < node.parentTree.numberOfColumns; ++j )
      {
         let font = node.font( j );
         font.pointSize = size;
         node.setFont( j, font );
      }
   };

   /**
    * Sets the font color for all cells of a node.
    *
    * @param {*} node the node to handle
    * @param {*} color the font color
    * @return {*}
    */
   this._setNodeFontColor = ( node, color ) =>
   {
      if ( !node.parentTree )
         return;
      for ( let j = 0; j < node.parentTree.numberOfColumns; ++j )
      {
         node.setTextColor( j, color );
      }
   };

   /**
    * Enables/disables a bold font for all cells of a node.
    *
    * @param {*} node the node to handle
    * @param {*} bold TRUE if the font has to be bold, FALSE otherwise
    * @return {*}
    */
   this._setNodeFontBold = ( node, bold ) =>
   {
      if ( !node.parentTree )
         return;
      for ( let j = 0; j < node.parentTree.numberOfColumns; ++j )
      {
         let font = node.font( j );
         font.bold = bold;
         node.setFont( j, font );
      }
   };

   /**
    * Deselects all nodes in all trees except the given node.
    *
    * @param {TreeBoxNode} exceptNode (optional) the node to be ignore
    */
   this._unselectAllNodesExcept = ( exceptNode ) =>
   {
      [ this.biasTreeBox, this.darkTreeBox, this.flatTreeBox, this.lightTreeBox ].forEach( treeBox =>
      {
         for ( let i = 0; i < treeBox.numberOfChildren; ++i )
         {
            let node = treeBox.child( i );
            if ( node != exceptNode )
               node.selected = false;
         }
      } );

      if ( !exceptNode )
      {
         this.selectedNode = null;
         this.selectedGroup = null;
         this.showGraphButton.enabled = false;
      }
   };

   // update could be called by async UI events so we prevent it from being called
   // while another execution is ongoing
   this.updateInProgress = false;

   /**
    * Regenerates from scratch the whole content of the treeBoxes.
    * To be called when new group is added or removed or, in general, when groups are
    * rebuilt.
    *
    * @return {*}
    */
   this.updateContent = () =>
   {
      if ( this.updateInProgress )
      {
         return;
      }
      this.updateInProgress = true;

      let treeBoxWithSelectionIndex = -1;
      let selectedNodeIndex = -1;
      for ( let i = 0; i < this.treeBoxes.length; ++i )
         if ( this.treeBoxes[ i ].selectedNodes.length > 0 )
         {
            treeBoxWithSelectionIndex = i;
            break;
         }

      if ( treeBoxWithSelectionIndex != -1 )
      {
         let treeBox = this.treeBoxes[ treeBoxWithSelectionIndex ];
         let node = treeBox.selectedNodes[ 0 ];
         for ( let j = 0; j < treeBox.numberOfChildren; ++j )
            if ( treeBox.child( j ) == node )
            {
               selectedNodeIndex = j;
               break;
            }
      }

      // swap the active treeboxes in order to render in background and avoid flipping
      this._swapActiveTrees();

      // clear the panel
      this._clearTable();

      this._setColumnHeaders();

      // get groups (only pre-process)
      let biasGroups = engine.getSortedGroupsOfType( ImageType.Bias, BPP.GroupingMode.PRE );
      let darkGroups = engine.getSortedGroupsOfType( ImageType.Dark, BPP.GroupingMode.PRE );
      let flatGroups = engine.getSortedGroupsOfType( ImageType.Flat, BPP.GroupingMode.PRE );
      let lightGroups = engine.getSortedGroupsOfType( ImageType.Light, BPP.GroupingMode.PRE );
      // filter out hidden groups
      lightGroups = lightGroups.filter( group => !group.isHidden );
      biasGroups.__imageType__ = ImageType.Bias;
      darkGroups.__imageType__ = ImageType.Dark;
      flatGroups.__imageType__ = ImageType.Flat;
      lightGroups.__imageType__ = ImageType.Light;

      let prepareTreeGroup = ( groups, treeBox ) =>
      {
         for ( let i = 0; i < groups.length; ++i )
         {
            let node = new TreeBoxNode( treeBox );
            // fill the Group <-> Node mapping
            this.groupNodeMap[ groups[ i ].id ] = node;
            node.__group__ = groups[ i ];
            this._fillGroupRowData( groups[ i ], node );
         }

         let height;
         if ( groups.__imageType__ == ImageType.Bias )
            height = 38 + Math.max( 2, groups.length ) * 24; // in logical pixels
         else
            height = 60 + Math.max( 2, groups.length ) * 26;

         if ( groups.__imageType__ == ImageType.Light )
            treeBox.setVariableHeight();
         else if ( groups.length <= 5 )
            treeBox.setScaledFixedHeight( height );
         else
            treeBox.setScaledMaxHeight( height );

         for ( let i = 0; i < treeBox.numberOfColumns; ++i )
            treeBox.adjustColumnWidthToContents( i );
         CoreApplication.processEvents();
         // Leave enough space in each column to change font weight to bold
         // without clipping cell text contents.
         for ( let i = 1; i < treeBox.numberOfColumns; ++i )
            treeBox.setColumnWidth( i, treeBox.columnWidth( i ) + this.logicalPixelsToPhysical( 16 ) );
      };

      prepareTreeGroup( biasGroups, this.biasTreeBox );
      prepareTreeGroup( darkGroups, this.darkTreeBox );
      prepareTreeGroup( flatGroups, this.flatTreeBox );
      prepareTreeGroup( lightGroups, this.lightTreeBox );

      this._resetTableAppearance( this.defaultFontColor );
      this.overscanSettingsControl.hideControls();
      this.calibrationSettingsControl.hideControls();
      this.pedestalSettingsControl.hideControls();
      this.cosmeticCorrectionSettingsControl.hideControls();
      this.debayerSettingsControl.hideControls();

      // re-select the previously selected node (if any) and refresh
      this.selectedGroup = undefined;
      this.selectedNode = undefined;
      this._updateTreeBoxNodeContents();
      this._updateStatusBox();
      this._updateShowGraphButton();

      if ( treeBoxWithSelectionIndex != -1 && selectedNodeIndex != -1 )
      {
         let treeBox = this.treeBoxes[ treeBoxWithSelectionIndex ];
         if ( selectedNodeIndex < treeBox.numberOfChildren )
         {
            let node = treeBox.child( selectedNodeIndex );
            node.selected = true;
            this._treeBoxRowSelectionUpdated( treeBox );
         }
      }

      this.swapTimer = new Timer( 0 /*interval*/ , false /*periodic*/ );
      this.swapTimer.onTimeout = () =>
      {
         this._makeActiveTreesVisible();
      };
      this.swapTimer.start();

      this.updateInProgress = false;
   };

   /**
    * Updates the selected row only. This function is convenient when some group information
    * has changed and affects only the visual information of the current row only.
    *
    */
   this.updateSelectedRow = () =>
   {
      if ( this.selectedNode != undefined )
         this._treeBoxRowSelectionUpdated( this.selectedNode.parentTree );
   };

   /**
    * Clears all treeboxes and resets the group-node map.
    *
    */
   this._clearTable = function()
   {
      this.treeBoxes.forEach( treeBox => treeBox.clear() );
      this.groupNodeMap = {};
   };

   /**
    * Populate the node with the given group's data
    *
    * @param {*} group the associated group
    * @param {*} node the node showing the group's information
    */
   this._fillGroupRowData = function( group, node )
   {
      let isCombinedRGB = group.associatedRGBchannel != undefined && group.associatedRGBchannel == BPP.AssociatedChannel.COMBINED_RGB;

      let name;
      if ( isCombinedRGB )
         name = "Recombined RGB (" + group.sizeString() + ")";
      else
         name = ( group.hasMaster ? "master" + StackEngine.imageTypeToString( group.imageType )
            : group.fileItems.length + " frame" + ( ( group.fileItems.length > 1 ) ? "s" : "" ) ) + " (" + group.sizeString() + ")";
      let binning = group.binning + "x" + group.binning;
      let exposure = ( group.imageType != ImageType.Bias ) ? group.exposureToString() : "";
      let filter = group.filter;
      let optimizeMasterDark = group.optimizeMasterDark;
      let hasMaster = group.hasMaster;
      let lightOutputPedestal = group.lightOutputPedestal;

      let checkGreenIcon = ":/browser/enabled.png";
      let warningIcon = ":/icons/warning.png";
      let cancelIcon = ":/icons/cancel.png";
      let blackCrosslIcon = ":/workspace/close-inactive.png";
      let linkIcon = ":/icons/link.png";
      let rgbIcon = ":/toolbar/image-display-rgb.png";
      let grayIcon = ":/toolbar/image-display-value.png";
      let forceNoMaster = ":/icons/cancel.png";
      let invalidCC = ":/icons/warning.png";
      let ccIssueIcon = ":/icons/warning.png";

      let darkOptimizationYES = ":/icons/function.png";
      let keywordIndex = -1;

      // starting index of light-flat specific columns
      let index;

      switch ( group.imageType )
      {
         case ImageType.Bias:
            node.setText( 0, "" + ( group.__counter__ || "" ) );
            [ name, binning ].forEach( ( text, i ) => node.setText( i + 1, text ) );
            if ( group.hasOverscanInfo() )
            {
               node.setIcon( 3, this.scaledResource( checkGreenIcon ) );
               node.setToolTip( 3, group.getOverscanDescription() );
            }
            else
            {
               node.clearIcon( 3 );
               node.setToolTip( 3, "" );
            }
            keywordIndex = 4;
            break;

         case ImageType.Dark:
            node.setText( 0, "" + ( group.__counter__ || "" ) );
            [ name, binning, exposure ].forEach( ( text, i ) => node.setText( i + 1, text ) );
            node.setAlignment( 2, TextAlignment.Right );
            if ( group.hasOverscanInfo() )
            {
               node.setIcon( 4, this.scaledResource( checkGreenIcon ) );
               node.setToolTip( 4, group.getOverscanDescription() );
            }
            else
            {
               node.clearIcon( 4 );
               node.setToolTip( 4, "" );
            }
            keywordIndex = 5;
            break;

         case ImageType.Flat:
         case ImageType.Light:
            node.setText( 0, "" + ( group.__counter__ || "" ) );
            // name, binning, exposure and filter
            [ name, binning, exposure, filter ].forEach( ( text, i ) => node.setText( i + 1, text ) );
            node.setAlignment( 3, TextAlignment.Right );
            index = 5;

            // Status - Flat Group
            // Status - Light Group
            let status = group.status();
            if ( status.errors )
               node.setIcon( index, this.scaledResource( cancelIcon ) );
            else if ( status.warnings )
               node.setIcon( index, this.scaledResource( warningIcon ) );
            else
               node.setIcon( index, this.scaledResource( checkGreenIcon ) );
            index++;

            let calibrationGroups = engine.calibrationMatcher.getCalibrationGroupsFor( group );

            // bias
            if ( !hasMaster )
               if ( calibrationGroups.masterBias )
                  node.setIcon( index, this.scaledResource( checkGreenIcon ) );
               else
                  node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
            index++;

            // dark
            if ( !hasMaster )
            {
               if ( group.forceNoDark )
                  node.setIcon( index, this.scaledResource( forceNoMaster ) );
               else if ( group.overrideDark )
                  node.setIcon( index, this.scaledResource( linkIcon ) );
               else if ( calibrationGroups.masterDark )
                  node.setIcon( index, this.scaledResource( checkGreenIcon ) );
               else
                  node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
            }
            else
               node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
            index++;

            // flat
            if ( group.imageType == ImageType.Light )
            {
               if ( !hasMaster )
               {
                  if ( group.forceNoFlat )
                     node.setIcon( index, this.scaledResource( forceNoMaster ) );
                  else if ( group.overrideFlat )
                     node.setIcon( index, this.scaledResource( linkIcon ) );
                  else if ( calibrationGroups.masterFlat )
                     node.setIcon( index, this.scaledResource( checkGreenIcon ) );
                  else
                     node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
               }
               index++;
            }

            // optimized dark
            if ( !hasMaster )
            {
               if ( optimizeMasterDark )
               {
                  node.setIcon( index, this.scaledResource( darkOptimizationYES ) );
                  node.setText( index, "Yes" );
               }
               else
               {
                  node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
                  node.setText( index, "" );
               }
            }
            index++;

            // light output pedestal - LIGHT Group
            if ( !engine.fastMode )
               if ( group.imageType == ImageType.Light )
               {
                  if ( group.lightOutputPedestalMode == ImageCalibration.OutputPedestal_Auto )
                     node.setText( index, format( "AUTO (%.2f%%)", 100 * group.lightOutputPedestalLimit ) );
                  else
                     node.setText( index, lightOutputPedestal.toString() );

                  node.setAlignment( index, TextAlignment.Right );
                  index++;
               }

            // light output cosmetic correction - LIGHT Group
            if ( group.imageType == ImageType.Light )
            {
               if ( group.ccData.enabled )
               {
                  let errorMsg = group.validateCC( calibrationGroups.masterDark );
                  if ( errorMsg )
                     node.setIcon( index, this.scaledResource( ccIssueIcon ) );
                  else
                     node.setIcon( index, this.scaledResource( checkGreenIcon ) );
                  node.setText( index, format( "AUTO (%i)", group.ccData.highSigma ) );
               }
               else if ( group.ccData.CCTemplate && group.ccData.CCTemplate.length > 0 )
               {
                  if ( WBPPUtils.validCCIconName( group.ccData.CCTemplate ) )
                     node.setIcon( index, this.scaledResource( checkGreenIcon ) );
                  else
                     node.setIcon( index, this.scaledResource( invalidCC ) );
                  node.setText( index, group.ccData.CCTemplate );
               }
               else
               {
                  node.setIcon( index, this.scaledResource( blackCrosslIcon ) );
                  node.setText( index, "" );
               }
               index++;
            }

            // CFA Images - Pattern and Methods
            if ( group.isCFA )
            {
               node.setIcon( index, this.scaledResource( rgbIcon ) );
               if ( group.imageType == ImageType.Flat )
                  node.setText( index, "Yes" );
               else
                  node.setText( index, group.CFAPatternString() + ", " + group.debayerMethodString() );
            }
            else
            {
               node.setIcon( index, this.scaledResource( grayIcon ) );
               node.setText( index, "No" );
            }
            index++;

            // Overscan Info
            if ( group.imageType == ImageType.Flat )
            {
               if ( group.hasOverscanInfo() )
               {
                  node.setIcon( index, this.scaledResource( checkGreenIcon ) );
                  node.setToolTip( index, group.getOverscanDescription() );
               }
               else
               {
                  node.clearIcon( index );
                  node.setToolTip( index, "" );
               }
               index++;
            }

            keywordIndex = index;
      }


      // fill the keyword values
      engine.keywords.keywordsForMode( BPP.GroupingMode.PRE ).forEach( keyword =>
      {
         let value = group.keywords[ keyword.name ] || "-";
         node.setText( keywordIndex, value );
         node.setToolTip( keywordIndex, value );
         keywordIndex++;
      } );
   };

   this.deselectNode = () =>
   {
      this.treeBoxes.forEach( t =>
      {
         for ( let i = 0; i < t.numberOfChildren; ++i )
            t.child( i ).selected = false;
      } )
      this.updateContent();
   };

   // initialize
   this.updateContent();
   }
}

// ----------------------------------------------------------------------------
/**
 * PostCalibration panel to handle the list of post-calibration groups.
 */
var PostCalibrationPanel = class extends Control
{
   constructor( parent )
   {
      super( parent );

   // styles
   this.optionsPanelWidth = parent.logicalPixelsToPhysical( 240 );

   // global maps of the group.id with the note in the tree boxes
   this.groupNodeMap = {};
   this.selectedGroup = undefined;
   this.selectedNode = undefined;

   // active calibration group
   this.graphCalibrationLight = null;

   // tree box descriptor
   this.lightDescriptor = new GroupTreeBoxDescriptor( ImageType.Light );

   // ---
   // GUI
   // ---

   // create the tree box listing the groups
   this.lightTreeBox = WBPPUtils.factory.CPTreeBox( parent );

   // Logic to be performed when a row is selected in a treebox
   this._treeBoxRowSelectionUpdated = () =>
   {
      if ( this.lightTreeBox.selectedNodes.length == 0 )
      {
         this.selectedNode = undefined;
         this.selectedGroup = undefined;
      }
      else
      {
         this.selectedNode = this.lightTreeBox.selectedNodes[ 0 ];
         this.selectedGroup = this.selectedNode.__group__;
      }
      this.updatePostControls();
   };

   // updates the drizzle controls with the selected group data
   this.updatePostControls = () =>
   {
      this.lightExposureToleranceSpinBox.value = engine.lightExposureTolerancePost;
      this.postProcessConfig.updateContent();

      // update controls that are visible only if a group is selected
      if ( this.selectedGroup )
      {
         this.drizzleConfig.updateWithGroup( this.selectedGroup );
         this.fastIntegrationConfig.updateWithGroup( this.selectedGroup );
      }

      // show the status message if needed
      let status = this.selectedGroup ? this.selectedGroup.status()
         :
         {};
      this.statusTextBox.visible = ( status.errors || status.warnings ) != undefined;
      this.statusTextBox.text = "<b><u>" + ( status.errors ? "ERRORS" : "WARNINGS" ) + "</u></b><br><br>" + ( status.errors || status.warnings || "" );
      this.statusTextBox.foregroundColor = status.errors ? 0xFFFF0000 : 0xFF333333;
      this.statusTextBox.home();
   }

   // update the whole Control Panel data
   this._updateTreeBoxNodeContents = () =>
   {
      // update all nodes content
      engine.groupsManager.groupsForMode( BPP.GroupingMode.POST ).forEach( group =>
      {
         let node = this.groupNodeMap[ group.id ];
         if ( node )
            this._fillGroupRowData( group, node );
      } );
   };

   // add one column for each keyword after the status column
   this._setColumnHeaders = () =>
   {
      let headers = this.lightDescriptor.headers( BPP.GroupingMode.POST );

      this.lightTreeBox.numberOfColumns = headers.length;
      for ( let i = 0; i < headers.length; ++i )
      {
         this.lightTreeBox.setHeaderAlignment( i, TextAlignment.Center );
         if ( headers[ i ] )
            this.lightTreeBox.setHeaderText( i, headers[ i ] );
         else
            this.lightTreeBox.setHeaderText( i, "" );
      };

      // MANUALLY SET the integration time
      let totalIntegrationTime = WBPPUtils.formatTimeDuration( engine.groupsManager.totalIntegrationTime() );
      this.lightTreeBox.setHeaderText( 5, "Integration Time\n" + totalIntegrationTime );

      let keywordsForMode = engine.keywords.keywordsForMode( BPP.GroupingMode.POST );
      let nKeywords = keywordsForMode.length;

      let lightBaseColumns = this.lightDescriptor.headers( BPP.GroupingMode.POST ).length;
      this.lightTreeBox.numberOfColumns = lightBaseColumns + nKeywords + 1;

      keywordsForMode.forEach( ( kw, i ) =>
      {
         this.lightTreeBox.setHeaderText( lightBaseColumns + i, kw.name );
         this.lightTreeBox.setHeaderAlignment( lightBaseColumns + i, TextAlignment.Center );
      } );

      // remove the header title from the last column
      this.lightTreeBox.setHeaderText( lightBaseColumns + nKeywords, "" );
   };

   // set the treeBox event handlers for all treeBoxes
   this.lightTreeBox.onNodeSelectionUpdated = this._treeBoxRowSelectionUpdated;

   // the right side controls container
   this.rightContainer = new Control( this );
   this.rightContainer.setFixedWidth( this.optionsPanelWidth );

   // show the post process configurations

   let lightExposureTooltip = "<p>Light frames with exposure times differing less than this value "
      + "(in seconds) will be grouped into the same master.</p>";

   this.lightExposureToleranceLabel = new Label( this );
   this.lightExposureToleranceLabel.text = "Exposure tolerance:";
   this.lightExposureToleranceLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.lightExposureToleranceLabel.toolTip = lightExposureTooltip;

   this.lightExposureToleranceSpinBox = new SpinBox( this );
   this.lightExposureToleranceSpinBox.minValue = 0;
   this.lightExposureToleranceSpinBox.maxValue = 3600;
   this.lightExposureToleranceSpinBox.toolTip = lightExposureTooltip;
   this.lightExposureToleranceSpinBox.onValueUpdated = function( value )
   {
      engine.lightExposureTolerancePost = value;
      parent.updateControls();
   };

   this.postExposureToleranceSizer = new HorizontalSizer;
   this.postExposureToleranceSizer.spacing = 4;
   this.postExposureToleranceSizer.addSpacing( 4 );
   this.postExposureToleranceSizer.add( this.lightExposureToleranceLabel );
   this.postExposureToleranceSizer.add( this.lightExposureToleranceSpinBox );
   this.postExposureToleranceSizer.addStretch();

   this.postProcessConfig = new PostProcessingConfiguration( this.rightContainer );
   this.postProcessConfig.setFixedWidth( this.optionsPanelWidth );

   this.drizzleConfig = new DrizzleConfiguration( this.rightContainer );
   this.drizzleConfig.setFixedWidth( this.optionsPanelWidth );
   this.drizzleConfig.onChange = () =>
   {
      parent.updateControls();
   }


   this.fastIntegrationConfig = new FastIntegrationConfiguration( this.rightContainer );
   this.fastIntegrationConfig.setFixedWidth( this.optionsPanelWidth );
   this.fastIntegrationConfig.onChange = () =>
   {
      parent.updateControls();
   }

   //

   // the status textbox reporting the detected issues of the selected groups
   this.statusTextBox = new TextBox( this.rightContainer );
   this.statusTextBox.readOnly = true;
   this.statusTextBox.styleSheet = "pi--PixInsightConsole { "
      + "font-family: Hack, DejaVu Sans Mono, Monospace; font-size: 10pt; background: white; }";
   this.statusTextBox.setFixedWidth( this.optionsPanelWidth );
   this.statusTextBox.setMinHeight( 0 );

   //

   // bottom sizer
   this.rightContainer.sizer = new VerticalSizer;
   let optionsSizer = this.rightContainer.sizer;
   optionsSizer.spacing = 4;

   optionsSizer.add( this.postExposureToleranceSizer );
   optionsSizer.add( this.postProcessConfig );
   optionsSizer.add( this.drizzleConfig );
   optionsSizer.add( this.fastIntegrationConfig );
   optionsSizer.add( this.statusTextBox );
   optionsSizer.addStretch();

   if ( engine.fastMode )
   {
      this.postProcessConfig.visible = false;
      this.postProcessConfig.__alwaysHidden__ = true;
   }

   // layout elements
   this.sizer = new HorizontalSizer;
   this.sizer.margin = 4;
   this.sizer.spacing = 4;
   this.sizer.add( this.lightTreeBox );
   this.sizer.add( this.rightContainer );

   // -------------------
   // AUXILIARY FUNCTIONS
   // -------------------

   // update (regenerate from scratch) the whole content of the treeBoxes.
   // to be called when new group is added or removed
   // update could be called by async UI events so we prevent it from being called
   // while another execution is ongoing
   this.updateInProgress = false;
   this.updateContent = () =>
   {
      if ( this.updateInProgress )
      {
         return;
      }
      this.updateInProgress = true;

      let selectedGroupID = this.selectedGroup ? this.selectedGroup.id : undefined;

      // clear the panel
      this.groupNodeMap = {};
      this.lightTreeBox.clear();

      this._setColumnHeaders();

      // get groups (only post-process)
      let lightGroups = engine.getSortedGroupsOfType( ImageType.Light, BPP.GroupingMode.POST );
      // filter out hidden groups
      lightGroups = lightGroups.filter( group => !group.isHidden );
      lightGroups.__imageType__ = ImageType.Light;

      // prepare the tree box
      for ( let i = 0; i < lightGroups.length; ++i )
      {
         let node = new TreeBoxNode( this.lightTreeBox );
         // fill the Group <-> Node mapping
         this.groupNodeMap[ lightGroups[ i ].id ] = node;
         node.__group__ = lightGroups[ i ];
         this._fillGroupRowData( lightGroups[ i ], node );
      }


      let height;
      if ( lightGroups.__imageType__ == ImageType.Bias )
         height = 38 + Math.max( 2, lightGroups.length ) * 24; // in logical pixels
      else
         height = 60 + Math.max( 2, lightGroups.length ) * 26;

      if ( lightGroups.__imageType__ == ImageType.Light )
         this.lightTreeBox.setVariableHeight();
      else if ( lightGroups.length <= 5 )
         this.lightTreeBox.setScaledFixedHeight( height );
      else
         this.lightTreeBox.setScaledMaxHeight( height );

      for ( let i = 0; i < this.lightTreeBox.numberOfColumns; ++i )
         this.lightTreeBox.adjustColumnWidthToContents( i );

      // Leave enough space in each column to change font weight to bold
      // without clipping cell text contents.
      for ( let i = 0; i < this.lightTreeBox.numberOfColumns; ++i )
         this.lightTreeBox.setColumnWidth( i, this.lightTreeBox.columnWidth( i ) + this.logicalPixelsToPhysical( 16 ) );

      // reselect the active group and refresh
      this.selectedGroup = undefined;
      this.selectedNode = undefined;

      if ( selectedGroupID )
      {
         // reselect the same group if listed
         for ( let i = 0; i < lightGroups.length; ++i )
            if ( lightGroups[ i ].id == selectedGroupID )
            {
               this.selectedGroup = lightGroups[ i ];
               this.selectedNode = this.lightTreeBox.child( i );
               this.selectedNode.selected = true;
               break;
            }
      }
      else if ( lightGroups.length > 0 )
      {
         this.selectedGroup = lightGroups[ 0 ];
         this.selectedNode = this.lightTreeBox.child( 0 );
         this.selectedNode.selected = true;
      }

      this._updateTreeBoxNodeContents();
      this.updatePostControls();

      this.updateInProgress = false;
   };

   // Populate the row corresponding to the given group
   this._fillGroupRowData = function( group, node )
   {

      // gather some basic information
      let isCombinedRGB = group.associatedRGBchannel != undefined && group.associatedRGBchannel == BPP.AssociatedChannel.COMBINED_RGB;
      let name;
      if ( isCombinedRGB )
         name = "Recombined RGB (" + group.sizeString() + ")";
      else
         name = ( group.hasMaster ? "master" + StackEngine.imageTypeToString( group.imageType )
            : group.fileItems.length + " frame" + ( ( group.fileItems.length > 1 ) ? "s" : "" ) ) + " (" + group.sizeString() + ")";

      let binning = group.binning + "x" + group.binning;
      let exposure = group.exposureTimesMinMaxRangeString();
      let filter = group.filter;

      // icon names
      let rgbIcon = ":/toolbar/image-display-rgb.png";
      let grayIcon = ":/toolbar/image-display-value.png";
      let checked = ":/qss/checkbox-checked.png";
      let checkGreenIcon = ":/browser/enabled.png";
      let warningIcon = ":/icons/warning.png";
      let saveAllIcon = ":/icons/save-all.png";
      let weightsEnabledIcon = ":/icons/chart.png";

      // init aux variables
      let keywordIndex = -1;

      // name, binning, exposure and filter
      [ name, binning, exposure, filter ].forEach( ( text, i ) => node.setText( i, text ) );
      node.setAlignment( 2, TextAlignment.Right );
      // starting index of light-flat specific columns
      let index = 4;

      // Color Space
      if ( group.isCFA )
      {
         node.setIcon( index, this.scaledResource( rgbIcon ) );
         node.setText( index, "RGB" );
      }
      else
      {
         node.setIcon( index, this.scaledResource( grayIcon ) );
         node.setText( index, group.associatedRGBchannel || "Gray" );
      }
      index++;

      // exposure time
      let totalExposureTime;
      if ( isCombinedRGB )
      {
         // the exposure comes from the parent group
         let postGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );
         for ( let i = 0; i < postGroups.length; ++i )
         {
            if ( postGroups[ i ].id == group.linkedGroupID )
            {
               totalExposureTime = postGroups[ i ].totalExposureTime()
               break;
            }
         }
      }
      else
         totalExposureTime = group.totalExposureTime()
      node.setText( index, WBPPUtils.formatTimeDuration( totalExposureTime ) );
      index++;


      // Fast Integration column
      if ( group.fastIntegrationData.enabled )
      {
         if ( group.fastIntegrationData.saveRegisteredImages )
            node.setIcon( index, this.scaledResource( saveAllIcon ) );
         else if ( group.fastIntegrationData.weightingScheme > 0 )
            node.setIcon( index, this.scaledResource( weightsEnabledIcon ) );
         else
            node.clearIcon( index );

         if ( group.fastIntegrationData.weightingScheme == 0 )
            node.setText( index, "no weighting" );
         else if ( group.fastIntegrationData.weightingScheme == 1 )
            node.setText( index, "PSF SNR weights" );
         else if ( group.fastIntegrationData.weightingScheme == 2 )
            node.setText( index, "Resolution weights" );
         else
            node.setText( index, "" );
      }
      else
      {
         node.clearIcon( index );
         node.setText( index, "" );
      }
      index++;

      // Drizzle column
      if ( !group.isDrizzleEnabled() )
      {
         if ( !group.isDrizzleAvailable() )
         {
            if ( group.isVirtual() )
            {
               node.setText( index, "not applicable" );
            }
            else
            {
               node.setText( index, "not compatible (SuperPixel debayer)" );
            }
         }
         else
            node.setText( index, "disabled" );
         node.clearIcon( index );
         node.setTextColor( index, 0xFFAAAAAA );
      }
      else
      {
         node.setIcon( index, this.scaledResource( checked ) );
         let info = ( group.drizzleFast() ? "Fast " : "" ) + group.drizzleScale() + "x, " + format( "%.2f", group.drizzleDropShrink() ) + ", " + group.getDrizzleFunctionName();
         let gridSize = group.getDrizzleGridSizeString();
         if ( gridSize.length > 0 )
            info += ", " + gridSize;
         node.setText( index, info );
         node.setTextColor( index, 0xFF000000 );
      }
      index++;

      // Status column
      let status = group.status();
      if ( ( status.errors || status.warnings ) == undefined )
         node.setIcon( index, this.scaledResource( checkGreenIcon ) );
      else
         node.setIcon( index, this.scaledResource( warningIcon ) );

      index++;

      // KEYWORDS

      keywordIndex = index;

      // fill the keyword values
      engine.keywords.keywordsForMode( BPP.GroupingMode.POST ).forEach( keyword =>
      {
         let value = group.keywords[ keyword.name ] || "-";
         node.setText( keywordIndex, value );
         node.setToolTip( keywordIndex, value );
         keywordIndex++;
      } );
   };

   // initialize
   this.updateContent();
   }
}

// ----------------------------------------------------------------------------

var OverscanRectControl = class extends Control
{
   constructor( parent, overscan, sourceRegion )
   {
      if ( parent )
         super( parent );
      else
         super();

   let editWidth1 = 7 * this.font.width( "0" );

   this.label = new Label( this );
   this.label.text = ( ( overscan < 0 ) ? "Image" : ( sourceRegion ? "Source" : "Target" ) ) + " region:";
   this.label.minWidth = this.dialog.labelWidth1;
   this.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   let fullName = "Overscan " + ( ( overscan < 0 ) ? "image" : "#" + ( overscan + 1 ).toString() + ( sourceRegion ? " source" : " target" ) ) + " region";

   this.leftControl = new NumericEdit( this );
   this.leftControl.overscan = overscan;
   this.leftControl.sourceRegion = sourceRegion;
   this.leftControl.label.hide();
   this.leftControl.setReal( false );
   this.leftControl.setRange( 0, 9999999 )
   this.leftControl.edit.setFixedWidth( editWidth1 );
   this.leftControl.toolTip = "<p>Left coordinate of the " + fullName + " in sensor pixels.</p>";
   this.leftControl.onValueUpdated = function( value )
   {
      let ivalue = Math.trunc( value );
      if ( this.overscan < 0 )
         engine.overscan.imageRect.x0 = ivalue;
      else if ( this.sourceRegion )
         engine.overscan.overscan[ this.overscan ].sourceRect.x0 = ivalue;
      else
         engine.overscan.overscan[ this.overscan ].targetRect.x0 = ivalue;
   };

   this.topControl = new NumericEdit( this );
   this.topControl.overscan = overscan;
   this.topControl.sourceRegion = sourceRegion;
   this.topControl.label.hide();
   this.topControl.setReal( false );
   this.topControl.setRange( 0, 9999999 )
   this.topControl.edit.setFixedWidth( editWidth1 );
   this.topControl.toolTip = "<p>Top coordinate of the " + fullName + " in sensor pixels.</p>";
   this.topControl.onValueUpdated = function( value )
   {
      let ivalue = Math.trunc( value );
      if ( this.overscan < 0 )
         engine.overscan.imageRect.y0 = ivalue;
      else if ( this.sourceRegion )
         engine.overscan.overscan[ this.overscan ].sourceRect.y0 = ivalue;
      else
         engine.overscan.overscan[ this.overscan ].targetRect.y0 = ivalue;
   };

   this.widthControl = new NumericEdit( this );
   this.widthControl.overscan = overscan;
   this.widthControl.sourceRegion = sourceRegion;
   this.widthControl.label.hide();
   this.widthControl.setReal( false );
   this.widthControl.setRange( 0, 9999999 )
   this.widthControl.edit.setFixedWidth( editWidth1 );
   this.widthControl.toolTip = "<p>Width of the " + fullName + " in sensor pixels.</p>";
   this.widthControl.onValueUpdated = function( value )
   {
      let ivalue = Math.trunc( value );
      if ( this.overscan < 0 )
      {
         engine.overscan.imageRect.x1 = engine.overscan.imageRect.x0 + ivalue;
         parent.dialog.updateControls();
      }
      else if ( this.sourceRegion )
         engine.overscan.overscan[ this.overscan ].sourceRect.x1 = engine.overscan.overscan[ this.overscan ].sourceRect.x0 + ivalue;
      else
         engine.overscan.overscan[ this.overscan ].targetRect.x1 = engine.overscan.overscan[ this.overscan ].targetRect.x0 + ivalue;
   };

   this.heightControl = new NumericEdit( this );
   this.heightControl.overscan = overscan;
   this.heightControl.sourceRegion = sourceRegion;
   this.heightControl.label.hide();
   this.heightControl.setReal( false );
   this.heightControl.setRange( 0, 9999999 )
   this.heightControl.edit.setFixedWidth( editWidth1 );
   this.heightControl.toolTip = "<p>Height of the " + fullName + " in sensor pixels.</p>";
   this.heightControl.onValueUpdated = function( value )
   {
      let ivalue = Math.trunc( value );
      if ( this.overscan < 0 )
      {
         engine.overscan.imageRect.y1 = engine.overscan.imageRect.y0 + ivalue;
         parent.dialog.updateControls();
      }
      else if ( this.sourceRegion )
         engine.overscan.overscan[ this.overscan ].sourceRect.y1 = engine.overscan.overscan[ this.overscan ].sourceRect.y0 + ivalue;
      else
         engine.overscan.overscan[ this.overscan ].targetRect.y1 = engine.overscan.overscan[ this.overscan ].targetRect.y0 + ivalue;
   };

   this.toolTip = "<p>" + fullName + ".</p>";

   this.sizer = new HorizontalSizer;
   this.sizer.spacing = 4;
   this.sizer.add( this.label );
   this.sizer.add( this.leftControl );
   this.sizer.add( this.topControl );
   this.sizer.add( this.widthControl );
   this.sizer.add( this.heightControl );
   this.sizer.addStretch();
   }
}

// ----------------------------------------------------------------------------

var OverscanRegionControl = class extends Control
{
   constructor( parent, overscan )
   {
      if ( parent )
         super( parent );
      else
         super();

   if ( overscan < 0 )
   {
      this.imageRectControl = new OverscanRectControl( this, overscan, false );

      this.sizer = new VerticalSizer;
      this.sizer.add( this.imageRectControl );
   }
   else
   {
      this.applyCheckBox = new CheckBox( this );
      this.applyCheckBox.overscan = overscan;
      this.applyCheckBox.text = "Overscan #" + ( overscan + 1 ).toString();
      this.applyCheckBox.toolTip = "<p>Enable overscan region #" + ( overscan + 1 ).toString() + ".</p>";
      this.applyCheckBox.onCheck = function( checked )
      {
         engine.overscan.overscan[ this.overscan ].enabled = checked;
         let biasPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Bias ) );
         biasPage.overscanControl.updateControls();
      };

      this.applySizer = new HorizontalSizer;
      this.applySizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
      this.applySizer.add( this.applyCheckBox );
      this.applySizer.addStretch();

      this.sourceRectControl = new OverscanRectControl( this, overscan, true );
      this.targetRectControl = new OverscanRectControl( this, overscan, false );

      this.sizer = new VerticalSizer;
      this.sizer.spacing = 4;
      this.sizer.add( this.applySizer );
      this.sizer.add( this.sourceRectControl );
      this.sizer.add( this.targetRectControl );
   }
   }
}

// ----------------------------------------------------------------------------

var OverscanControl = class extends ParametersControl
{
   constructor( parent, expand )
   {
      super( "Overscan", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ );

   //

   this.imageControl = new OverscanRegionControl( this, -1 );
   this.overscanControls = new Array;
   this.overscanControls.push( new OverscanRegionControl( this, 0 ) );
   this.overscanControls.push( new OverscanRegionControl( this, 1 ) );
   this.overscanControls.push( new OverscanRegionControl( this, 2 ) );
   this.overscanControls.push( new OverscanRegionControl( this, 3 ) );

   this.add( this.imageControl );
   this.add( this.overscanControls[ 0 ] );
   this.add( this.overscanControls[ 1 ] );
   this.add( this.overscanControls[ 2 ] );
   this.add( this.overscanControls[ 3 ] );

   this.updateControls = function()
   {
      this.imageControl.imageRectControl.leftControl.setValue( engine.overscan.imageRect.x0 );
      this.imageControl.imageRectControl.topControl.setValue( engine.overscan.imageRect.y0 );
      this.imageControl.imageRectControl.widthControl.setValue( engine.overscan.imageRect.width );
      this.imageControl.imageRectControl.heightControl.setValue( engine.overscan.imageRect.height );

      for ( let i = 0; i < 4; ++i )
      {
         let enabled = engine.overscan.overscan[ i ].enabled;
         this.overscanControls[ i ].applyCheckBox.checked = enabled;
         this.overscanControls[ i ].sourceRectControl.leftControl.setValue( engine.overscan.overscan[ i ].sourceRect.x0 );
         this.overscanControls[ i ].sourceRectControl.topControl.setValue( engine.overscan.overscan[ i ].sourceRect.y0 );
         this.overscanControls[ i ].sourceRectControl.widthControl.setValue( engine.overscan.overscan[ i ].sourceRect.width );
         this.overscanControls[ i ].sourceRectControl.heightControl.setValue( engine.overscan.overscan[ i ].sourceRect.height );
         this.overscanControls[ i ].sourceRectControl.enabled = enabled;
         this.overscanControls[ i ].targetRectControl.leftControl.setValue( engine.overscan.overscan[ i ].targetRect.x0 );
         this.overscanControls[ i ].targetRectControl.topControl.setValue( engine.overscan.overscan[ i ].targetRect.y0 );
         this.overscanControls[ i ].targetRectControl.widthControl.setValue( engine.overscan.overscan[ i ].targetRect.width );
         this.overscanControls[ i ].targetRectControl.heightControl.setValue( engine.overscan.overscan[ i ].targetRect.height );
         this.overscanControls[ i ].targetRectControl.enabled = enabled;
      }

      this.contents.enabled = engine.overscan.enabled;
   };

   this.reset = function()
   {
      engine.defaults.overscan();
      this.updateControls();
   };
   }
}

// ----------------------------------------------------------------------------

var BiasOverscanControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Overscan", parent );

   //

   this.applyCheckBox = new CheckBox( this );
   this.applyCheckBox.text = "Apply";
   this.applyCheckBox.toolTip = "<p>Apply overscan correction.</p>";
   this.applyCheckBox.onCheck = function( checked )
   {
      engine.overscan.enabled = checked;
      this.dialog.updateControls();
   };

   this.applySizer = new HorizontalSizer;
   if ( !engine.fastMode )
      this.applySizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.applySizer.add( this.applyCheckBox );
   this.applySizer.addStretch();

   //

   this.editButton = new PushButton( this );
   this.editButton.text = "Overscan parameters...";
   this.editButton.icon = this.scaledResource( ":/icons/arrow-right.png" );
   this.editButton.toolTip = "<p>Edit overscan parameters.</p>";
   this.editButton.onClick = function()
   {
      let biasPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Bias ) );
      biasPage.overscanControl.makeVisible();
   };

   this.editSizer = new HorizontalSizer;
   if ( !engine.fastMode )
      this.editSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.editSizer.add( this.editButton );
   this.editSizer.addStretch();

   //

   this.add( this.applySizer );
   this.add( this.editSizer );

   this.updateControls = function()
   {
      this.applyCheckBox.checked = engine.overscan.enabled;
      this.editButton.enabled = engine.overscan.enabled;
   };
   }
}

// ----------------------------------------------------------------------------

var ImageIntegrationControl = class extends ParametersControl
{
   constructor( parent, imageType, expand )
   {
      super( "Image Integration", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ );

   this.imageType = imageType;

   let IIlabelWidth = this.font.width( "Large-scale pixel rejection: " + "M" );

   //

   this.combinationLabel = new Label( this );
   this.combinationLabel.text = "Combination:";
   this.combinationLabel.minWidth = IIlabelWidth;
   this.combinationLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.combinationComboBox = new ComboBox( this );
   this.combinationComboBox.addItem( "Average" );
   this.combinationComboBox.addItem( "Median" );
   this.combinationComboBox.addItem( "Minimum" );
   this.combinationComboBox.addItem( "Maximum" );
   this.combinationComboBox.onItemSelected = function( item )
   {
      engine.combination[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = item;
   };

   this.combinationLabel.toolTip = this.combinationComboBox.toolTip =
      "<p><b>Average</b> combination provides the best signal-to-noise ratio in the integrated result.</p>"
      + "<p><b>Median</b> combination provides more robust rejection of outliers, but at the cost of more noise.</p>";

   this.combinationSizer = new HorizontalSizer;
   this.combinationSizer.spacing = 4;
   this.combinationSizer.add( this.combinationLabel );
   this.combinationSizer.add( this.combinationComboBox );
   this.combinationSizer.addStretch();

   //

   if ( this.imageType == ImageType.Light )
   {
      this.minWeightControl = new NumericEdit( this );
      this.minWeightControl.label.text = "Minimum weight:";
      this.minWeightControl.label.minWidth = IIlabelWidth;
      this.minWeightControl.setReal( true );
      this.minWeightControl.setRange( 0, 1 );
      this.minWeightControl.setPrecision( 6 );
      this.minWeightControl.sizer.addStretch();
      this.minWeightControl.toolTip =
         "<p>Minimum normalized weight required for integration.</p>"
         + "<p>Images with normalized weights below the value of this parameter will be excluded for integration. The default "
         + "value is 0.05, which represents a 5% of the maximum weight in the integrated data set. To disable this automatic "
         + "image exclusion feature, set this parameter to zero.</p>";
      this.minWeightControl.onValueUpdated = function( value )
      {
         engine.minWeight = value;
      };
   }

   //

   this.rejectionAlgorithmLabel = new Label( this );
   this.rejectionAlgorithmLabel.text = "Rejection algorithm:";
   this.rejectionAlgorithmLabel.minWidth = IIlabelWidth;
   this.rejectionAlgorithmLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.rejectionAlgorithmComboBox = new ComboBox( this );
   let names = engine.rejectionNames();
   names.forEach( item => this.rejectionAlgorithmComboBox.addItem( item ) );
   this.rejectionAlgorithmComboBox.onItemSelected = function( item )
   {
      engine.rejection[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = engine.rejectionFromIndex( item );
      this.parent.parent.updateControls();
   };

   this.rejectionAlgorithmLabel.toolTip = this.rejectionAlgorithmComboBox.toolTip =
      "<p><b>Percentile clipping</b> rejection is excellent to integrate reduced sets of images, such as "
      + "3 to 6 images. This is a single-pass algorithm that rejects pixels outside a fixed range of values "
      + "relative to the median of each pixel stack.</p>"
      +

      "<p><b>Winsorized sigma clipping</b> is similar to the normal sigma clipping algorithm, but uses a "
      + "special iterative procedure based on Huber's method of robust estimation of parameters through "
      + "<i>Winsorization</i>. This algorithm can yield superior rejection of outliers with better preservation "
      + "of significant data for large sets of images.</p>"
      +

      "<p><b>Linear fit clipping</b> fits each pixel stack to a straight line. The linear fit is optimized "
      + "in the twofold sense of minimizing average absolute deviation and maximizing inliers. This rejection "
      + "algorithm is more robust than sigma clipping for large sets of images, especially in presence of "
      + "additive sky gradients of varying intensity and spatial distribution. For the best performance, use "
      + "this algorithm for large sets of at least 15 images. Five images is the minimum required.</p>"
      +

      "<p>The <b>Generalized Extreme Studentized Deviate (ESD)</b> rejection algorithm is an implementation "
      + "of the method described by Bernard Rosner in his 1983 paper <i>Percentage Points for a Generalized ESD "
      + "Many-Outlier procedure</i>, adapted to the image integration task. The ESD algorithm assumes that each "
      + "pixel stack, in absence of outliers, follows an approximately normal (Gaussian) distribution. It aims at "
      + "avoiding <i>masking</i>, a serious issue that occurs when an outlier goes undetected because its value is "
      + "similar to another outlier. The performance of this algorithm is excellent for data sets of 15 or more "
      + "images, although good results can also be obtained for reduced sets of 8-10 frames. The minimum required "
      + "is 3 images.</p>"
      +

      "<p><b>Robust Chauvenet Rejection (RCR)</b> is based on the algorithms described in Maples, M. P., "
      + "Reichart, D. E. et al., <i>Robust Chauvenet Outlier Rejection</i>, Astrophysical Journal Supplement "
      + "Series, 2018, 238, A2, 1-49. Our implementation applies three successive stages of rejection with "
      + "decreasingly robust/increasingly precise measures of central tendency and sample deviation, rejecting "
      + "a single pixel at each iteration for maximum stability. This is a single-parameter pixel rejection "
      + "algorithm introduced since version 1.8.9 of PixInsight.</p>"
      +

      "<p><b>Auto</b> selects the best algorithm depending on the amount of images in the group.</p>";

   this.rejectionAlgorithmSizer = new HorizontalSizer;
   this.rejectionAlgorithmSizer.spacing = 4;
   this.rejectionAlgorithmSizer.add( this.rejectionAlgorithmLabel );
   this.rejectionAlgorithmSizer.add( this.rejectionAlgorithmComboBox );
   this.rejectionAlgorithmSizer.addStretch();

   //

   this.percentileLowControl = new NumericControl( this );
   this.percentileLowControl.label.text = "Percentile low:";
   this.percentileLowControl.label.minWidth = IIlabelWidth;
   this.percentileLowControl.setRange( 0, 1 );
   this.percentileLowControl.slider.setRange( 0, 1000 );
   this.percentileLowControl.slider.scaledMinWidth = 200;
   this.percentileLowControl.setPrecision( 2 );
   this.percentileLowControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.percentileLowControl.toolTip = "<p>Low clipping factor for the percentile clipping rejection algorithm.</p>";
   this.percentileLowControl.onValueUpdated = function( value )
   {
      engine.percentileLow[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.percentileHighControl = new NumericControl( this );
   this.percentileHighControl.label.text = "Percentile high:";
   this.percentileHighControl.label.minWidth = IIlabelWidth;
   this.percentileHighControl.setRange( 0, 1 );
   this.percentileHighControl.slider.setRange( 0, 1000 );
   this.percentileHighControl.slider.scaledMinWidth = 200;
   this.percentileHighControl.setPrecision( 2 );
   this.percentileHighControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.percentileHighControl.toolTip = "<p>High clipping factor for the percentile clipping rejection algorithm.</p>";
   this.percentileHighControl.onValueUpdated = function( value )
   {
      engine.percentileHigh[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.sigmaLowControl = new NumericControl( this );
   this.sigmaLowControl.label.text = "Sigma low:";
   this.sigmaLowControl.label.minWidth = IIlabelWidth;
   this.sigmaLowControl.setRange( 0, 10 );
   this.sigmaLowControl.slider.setRange( 0, 1000 );
   this.sigmaLowControl.slider.scaledMinWidth = 200;
   this.sigmaLowControl.setPrecision( 2 );
   this.sigmaLowControl.setValue( 4.0 );
   this.sigmaLowControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.sigmaLowControl.toolTip = "<p>Low clipping factor for the sigma clipping rejection algorithms.</p>";
   this.sigmaLowControl.onValueUpdated = function( value )
   {
      engine.sigmaLow[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.sigmaHighControl = new NumericControl( this );
   this.sigmaHighControl.label.text = "Sigma high:";
   this.sigmaHighControl.label.minWidth = IIlabelWidth;
   this.sigmaHighControl.setRange( 0, 10 );
   this.sigmaHighControl.slider.setRange( 0, 1000 );
   this.sigmaHighControl.slider.scaledMinWidth = 200;
   this.sigmaHighControl.setPrecision( 2 );
   this.sigmaHighControl.setValue( 2.0 );
   this.sigmaHighControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.sigmaHighControl.toolTip = "<p>High clipping factor for the sigma clipping rejection algorithms.</p>";
   this.sigmaHighControl.onValueUpdated = function( value )
   {
      engine.sigmaHigh[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.linearFitLowControl = new NumericControl( this );
   this.linearFitLowControl.label.text = "Linear fit low:";
   this.linearFitLowControl.label.minWidth = IIlabelWidth;
   this.linearFitLowControl.setRange( 0, 10 );
   this.linearFitLowControl.slider.setRange( 0, 1000 );
   this.linearFitLowControl.slider.scaledMinWidth = 200;
   this.linearFitLowControl.setPrecision( 2 );
   this.linearFitLowControl.setValue( 5.0 );
   this.linearFitLowControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.linearFitLowControl.toolTip = "<p>Low clipping factor for the linear fit clipping rejection algorithm.</p>";
   this.linearFitLowControl.onValueUpdated = function( value )
   {
      engine.linearFitLow[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.linearFitHighControl = new NumericControl( this );
   this.linearFitHighControl.label.text = "Linear fit high:";
   this.linearFitHighControl.label.minWidth = IIlabelWidth;
   this.linearFitHighControl.setRange( 0, 10 );
   this.linearFitHighControl.slider.setRange( 0, 1000 );
   this.linearFitHighControl.slider.scaledMinWidth = 200;
   this.linearFitHighControl.setPrecision( 2 );
   this.linearFitHighControl.setValue( 2.5 );
   this.linearFitHighControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.linearFitHighControl.toolTip = "<p>High clipping factor for the linear fit clipping rejection algorithm.</p>";
   this.linearFitHighControl.onValueUpdated = function( value )
   {
      engine.linearFitHigh[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.ESD_OutliersControl = new NumericControl( this );
   this.ESD_OutliersControl.label.text = "ESD outliers:";
   this.ESD_OutliersControl.label.minWidth = IIlabelWidth;
   this.ESD_OutliersControl.setRange( 0, 1 );
   this.ESD_OutliersControl.slider.setRange( 0, 1000 );
   this.ESD_OutliersControl.slider.scaledMinWidth = 200;
   this.ESD_OutliersControl.setPrecision( 2 );
   this.ESD_OutliersControl.setValue( 0.3 );
   this.ESD_OutliersControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.ESD_OutliersControl.toolTip = "<p>Expected maximum fraction of outliers for the generalized ESD rejection algorithm.</p>"
      + "<p>For example, a value of 0.2 applied to a stack of 10 pixels means that the ESD algorithm will be limited to detect a maximum of "
      + "two outlier pixels, or in other words, only 0, 1 or 2 outliers will be detectable in such case. The default value is 0.3, which allows the algorithm "
      + "to detect up to a 30% of outlier pixels in each pixel stack.</p>";
   this.ESD_OutliersControl.onValueUpdated = function( value )
   {
      engine.ESD_Outliers[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.ESD_SignificanceControl = new NumericControl( this );
   this.ESD_SignificanceControl.label.text = "ESD significance:";
   this.ESD_SignificanceControl.label.minWidth = IIlabelWidth;
   this.ESD_SignificanceControl.setRange( 0, 1 );
   this.ESD_SignificanceControl.slider.setRange( 0, 1000 );
   this.ESD_SignificanceControl.slider.scaledMinWidth = 200;
   this.ESD_SignificanceControl.setPrecision( 2 );
   this.ESD_SignificanceControl.setValue( 0.05 );
   this.ESD_SignificanceControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.ESD_SignificanceControl.toolTip = "<p>Probability of making a type 1 error (false positive) in the generalized ESD rejection algorithm.</p>"
      + "<p>This is the significance level of the outlier detection hypothesis test. For example, a significance level of 0.01 means that a 1% chance "
      + "of being wrong when rejecting the null hypothesis (that there are no outliers in a given pixel stack) is acceptable. The default value is 0.05 "
      + "(5% significance level).</p>";
   this.ESD_SignificanceControl.onValueUpdated = function( value )
   {
      engine.ESD_Significance[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.RCR_Limit = new NumericControl( this );
   this.RCR_Limit.label.text = "RCR limit:";
   this.RCR_Limit.label.minWidth = IIlabelWidth;
   this.RCR_Limit.setRange( 0, 1 );
   this.RCR_Limit.slider.setRange( 0, 100 );
   this.RCR_Limit.slider.scaledMinWidth = 200;
   this.RCR_Limit.setPrecision( 2 );
   this.RCR_Limit.setValue( 0.1 );
   this.RCR_Limit.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.RCR_Limit.toolTip = "<p>Limit for the altered Chauvenet rejection criterion.</p > "
      + "<p>The larger the value of this parameter, the more pixels will be rejected by the Robust "
      + "Chauvenet Rejection algorithm.</p>";
   this.RCR_Limit.onValueUpdated = function( value )
   {
      engine.RCR_Limit[ BPP.imageTypeIndex( this.parent.parent.imageType ) ] = value;
   };

   //

   this.add( this.combinationSizer );
   if ( this.imageType == ImageType.Light )
      this.add( this.minWeightControl );
   this.add( this.rejectionAlgorithmSizer );
   this.add( this.percentileLowControl );
   this.add( this.percentileHighControl );
   this.add( this.sigmaLowControl );
   this.add( this.sigmaHighControl );
   this.add( this.linearFitLowControl );
   this.add( this.linearFitHighControl );
   this.add( this.ESD_OutliersControl );
   this.add( this.ESD_SignificanceControl );
   this.add( this.RCR_Limit );

   if ( this.imageType == ImageType.Flat )
   {
      this.flatLargeScaleRejectionCheckBox = new CheckBox( this );
      this.flatLargeScaleRejectionCheckBox.text = "Large-scale pixel rejection";
      this.flatLargeScaleRejectionCheckBox.toolTip = "<p>Apply large-scale pixel rejection, high pixel sample values. "
         + "Useful to improve rejection of stars for integration of sky flats.</p>";
      this.flatLargeScaleRejectionCheckBox.onCheck = function( checked )
      {
         engine.flatsLargeScaleRejection = checked;
         this.parent.parent.updateControls();
      };

      this.flatLargeScaleRejectionSizer = new HorizontalSizer;
      this.flatLargeScaleRejectionSizer.addUnscaledSpacing( IIlabelWidth + this.logicalPixelsToPhysical( 4 ) );
      this.flatLargeScaleRejectionSizer.add( this.flatLargeScaleRejectionCheckBox );
      this.flatLargeScaleRejectionSizer.addStretch();

      //

      this.flatLargeScaleRejectionLayersLabel = new Label( this );
      this.flatLargeScaleRejectionLayersLabel.text = "Large-scale layers:";
      this.flatLargeScaleRejectionLayersLabel.minWidth = IIlabelWidth;
      this.flatLargeScaleRejectionLayersLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

      this.flatLargeScaleRejectionLayersSpinBox = new SpinBox( this );
      this.flatLargeScaleRejectionLayersSpinBox.minValue = 1;
      this.flatLargeScaleRejectionLayersSpinBox.maxValue = 6;
      this.flatLargeScaleRejectionLayersSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.flatLargeScaleRejectionLayersSpinBox.onValueUpdated = function( value )
      {
         engine.flatsLargeScaleRejectionLayers = value;
      };

      this.flatLargeScaleRejectionLayersLabel.toolTip = this.flatLargeScaleRejectionLayersSpinBox.toolTip =
         "<p>Large-scale pixel rejection, number of protected small-scale wavelet layers. "
         + "Increase to restrict large-scale rejection to larger structures of contiguous rejected pixels.</p>";

      this.flatLargeScaleRejectionLayersSizer = new HorizontalSizer;
      this.flatLargeScaleRejectionLayersSizer.spacing = 4;
      this.flatLargeScaleRejectionLayersSizer.add( this.flatLargeScaleRejectionLayersLabel );
      this.flatLargeScaleRejectionLayersSizer.add( this.flatLargeScaleRejectionLayersSpinBox );
      this.flatLargeScaleRejectionLayersSizer.addStretch();

      //

      this.flatLargeScaleRejectionGrowthLabel = new Label( this );
      this.flatLargeScaleRejectionGrowthLabel.text = "Large-scale growth:";
      this.flatLargeScaleRejectionGrowthLabel.minWidth = IIlabelWidth;
      this.flatLargeScaleRejectionGrowthLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

      this.flatLargeScaleRejectionGrowthSpinBox = new SpinBox( this );
      this.flatLargeScaleRejectionGrowthSpinBox.minValue = 1;
      this.flatLargeScaleRejectionGrowthSpinBox.maxValue = 20;
      this.flatLargeScaleRejectionGrowthSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.flatLargeScaleRejectionGrowthSpinBox.onValueUpdated = function( value )
      {
         engine.flatsLargeScaleRejectionGrowth = value;
      };

      this.flatLargeScaleRejectionGrowthLabel.toolTip = this.flatLargeScaleRejectionGrowthSpinBox.toolTip =
         "<p>Large-scale pixel rejection, growth of large-scale pixel rejection structures. "
         + "Increase to extend rejection to more adjacent pixels.</p>";

      this.flatLargeScaleRejectionGrowthSizer = new HorizontalSizer;
      this.flatLargeScaleRejectionGrowthSizer.spacing = 4;
      this.flatLargeScaleRejectionGrowthSizer.add( this.flatLargeScaleRejectionGrowthLabel );
      this.flatLargeScaleRejectionGrowthSizer.add( this.flatLargeScaleRejectionGrowthSpinBox );
      this.flatLargeScaleRejectionGrowthSizer.addStretch();

      //

      this.add( this.flatLargeScaleRejectionSizer );
      this.add( this.flatLargeScaleRejectionLayersSizer );
      this.add( this.flatLargeScaleRejectionGrowthSizer );
   }

   if ( this.imageType == ImageType.Light )
   {
      this.lightLargeScaleRejectionLayersCheckboxesLabel = new Label( this );
      this.lightLargeScaleRejectionLayersCheckboxesLabel.text = "Large-scale pixel rejection:";
      this.lightLargeScaleRejectionLayersCheckboxesLabel.minWidth = IIlabelWidth;
      this.lightLargeScaleRejectionLayersCheckboxesLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
      this.lightLargeScaleRejectionLayersCheckboxesLabel.setMinHeight( this.logicalPixelsToPhysical( 10 ) );

      this.lightLargeScaleRejectionHighCheckBox = new CheckBox( this );
      this.lightLargeScaleRejectionHighCheckBox.text = "High";
      this.lightLargeScaleRejectionHighCheckBox.toolTip = "<p>Apply large-scale pixel rejection, high pixel sample values.";
      this.lightLargeScaleRejectionHighCheckBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionHighCheckBox.onCheck = function( checked )
      {
         engine.lightsLargeScaleRejectionHigh = checked;
         this.parent.parent.updateControls();
      };

      this.lightLargeScaleRejectionLowCheckBox = new CheckBox( this );
      this.lightLargeScaleRejectionLowCheckBox.text = "Low";
      this.lightLargeScaleRejectionLowCheckBox.toolTip = "<p>Apply large-scale pixel rejection, low pixel sample values.";
      this.lightLargeScaleRejectionLowCheckBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionLowCheckBox.onCheck = function( checked )
      {
         engine.lightsLargeScaleRejectionLow = checked;
         this.parent.parent.updateControls();
      };

      //

      this.lightLargeScaleRejectionLayersLabel = new Label( this );
      this.lightLargeScaleRejectionLayersLabel.text = "Large-scale layers:";
      this.lightLargeScaleRejectionLayersLabel.minWidth = IIlabelWidth;
      this.lightLargeScaleRejectionLayersLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
      this.lightLargeScaleRejectionLayersLabel.setMinHeight( this.logicalPixelsToPhysical( 10 ) );

      this.lightLargeScaleRejectionLayersHighSpinBox = new SpinBox( this );
      this.lightLargeScaleRejectionLayersHighSpinBox.minValue = 1;
      this.lightLargeScaleRejectionLayersHighSpinBox.maxValue = 6;
      this.lightLargeScaleRejectionLayersHighSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.lightLargeScaleRejectionLayersHighSpinBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionLayersHighSpinBox.onValueUpdated = function( value )
      {
         engine.lightsLargeScaleRejectionLayersHigh = value;
      };

      this.lightLargeScaleRejectionLayersLowSpinBox = new SpinBox( this );
      this.lightLargeScaleRejectionLayersLowSpinBox.minValue = 1;
      this.lightLargeScaleRejectionLayersLowSpinBox.maxValue = 6;
      this.lightLargeScaleRejectionLayersLowSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.lightLargeScaleRejectionLayersLowSpinBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionLayersLowSpinBox.onValueUpdated = function( value )
      {
         engine.lightsLargeScaleRejectionLayersLow = value;
      };

      this.lightLargeScaleRejectionLayersLabel.toolTip = this.lightLargeScaleRejectionLayersHighSpinBox.toolTip =
         this.lightLargeScaleRejectionLayersLowSpinBox.toolTip =
         "<p>Large-scale pixel rejection, number of protected small-scale wavelet layers. "
         + "Increase it to restrict large-scale rejection to larger structures of contiguous rejected pixels.</p>";

      //

      this.lightLargeScaleRejectionGrowthLabel = new Label( this );
      this.lightLargeScaleRejectionGrowthLabel.text = "Large-scale growth:";
      this.lightLargeScaleRejectionGrowthLabel.minWidth = IIlabelWidth;
      this.lightLargeScaleRejectionGrowthLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
      this.lightLargeScaleRejectionGrowthLabel.setMinHeight( this.logicalPixelsToPhysical( 10 ) );

      this.lightLargeScaleRejectionGrowthHighSpinBox = new SpinBox( this );
      this.lightLargeScaleRejectionGrowthHighSpinBox.minValue = 1;
      this.lightLargeScaleRejectionGrowthHighSpinBox.maxValue = 20;
      this.lightLargeScaleRejectionGrowthHighSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.lightLargeScaleRejectionGrowthHighSpinBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionGrowthHighSpinBox.onValueUpdated = function( value )
      {
         engine.lightsLargeScaleRejectionGrowthHigh = value;
      };

      this.lightLargeScaleRejectionGrowthLowSpinBox = new SpinBox( this );
      this.lightLargeScaleRejectionGrowthLowSpinBox.minValue = 1;
      this.lightLargeScaleRejectionGrowthLowSpinBox.maxValue = 20;
      this.lightLargeScaleRejectionGrowthLowSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
      this.lightLargeScaleRejectionGrowthLowSpinBox.setMinHeight( this.logicalPixelsToPhysical( 10 ) );
      this.lightLargeScaleRejectionGrowthLowSpinBox.onValueUpdated = function( value )
      {
         engine.lightsLargeScaleRejectionGrowthLow = value;
      };

      this.lightLargeScaleRejectionGrowthLabel.toolTip = this.lightLargeScaleRejectionGrowthLowSpinBox.toolTip =
         "<p>Large-scale pixel rejection, growth of large-scale pixel rejection structures. "
         + "Increase to extend rejection to more adjacent pixels.</p>";

      this.lightLargeScaleRejectionSizer1 = new VerticalSizer;
      this.lightLargeScaleRejectionSizer1.spacing = 4;
      this.lightLargeScaleRejectionSizer1.add( this.lightLargeScaleRejectionLayersCheckboxesLabel );
      this.lightLargeScaleRejectionSizer1.add( this.lightLargeScaleRejectionLayersLabel );
      this.lightLargeScaleRejectionSizer1.add( this.lightLargeScaleRejectionGrowthLabel );

      this.lightLargeScaleRejectionSizer2 = new VerticalSizer;
      this.lightLargeScaleRejectionSizer2.spacing = 4;
      this.lightLargeScaleRejectionSizer2.add( this.lightLargeScaleRejectionHighCheckBox );
      this.lightLargeScaleRejectionSizer2.add( this.lightLargeScaleRejectionLayersHighSpinBox );
      this.lightLargeScaleRejectionSizer2.add( this.lightLargeScaleRejectionGrowthHighSpinBox );

      this.lightLargeScaleRejectionSizer3 = new VerticalSizer;
      this.lightLargeScaleRejectionSizer3.spacing = 4;
      this.lightLargeScaleRejectionSizer3.add( this.lightLargeScaleRejectionLowCheckBox );
      this.lightLargeScaleRejectionSizer3.add( this.lightLargeScaleRejectionLayersLowSpinBox );
      this.lightLargeScaleRejectionSizer3.add( this.lightLargeScaleRejectionGrowthLowSpinBox );

      this.lightLargeScaleRejectionSizer = new HorizontalSizer;
      this.lightLargeScaleRejectionSizer.add( this.lightLargeScaleRejectionSizer1 );
      this.lightLargeScaleRejectionSizer.addSpacing( 4 );
      this.lightLargeScaleRejectionSizer.add( this.lightLargeScaleRejectionSizer2 );
      this.lightLargeScaleRejectionSizer.addSpacing( 8 );
      this.lightLargeScaleRejectionSizer.add( this.lightLargeScaleRejectionSizer3 );
      this.lightLargeScaleRejectionSizer.addStretch();

      this.add( this.lightLargeScaleRejectionSizer );
   }

   this.updateControls = function()
   {
      this.combinationComboBox.currentItem = engine.combination[ BPP.imageTypeIndex( this.imageType ) ] || 0;
      if ( this.imageType == ImageType.Light )
         this.minWeightControl.setValue( engine.minWeight );
      this.rejectionAlgorithmComboBox.currentItem = engine.rejectionIndex( engine.rejection[ BPP.imageTypeIndex( this.imageType ) ] );
      this.percentileLowControl.setValue( engine.percentileLow[ BPP.imageTypeIndex( this.imageType ) ] );
      this.percentileHighControl.setValue( engine.percentileHigh[ BPP.imageTypeIndex( this.imageType ) ] );
      this.sigmaLowControl.setValue( engine.sigmaLow[ BPP.imageTypeIndex( this.imageType ) ] );
      this.sigmaHighControl.setValue( engine.sigmaHigh[ BPP.imageTypeIndex( this.imageType ) ] );
      this.linearFitLowControl.setValue( engine.linearFitLow[ BPP.imageTypeIndex( this.imageType ) ] );
      this.linearFitHighControl.setValue( engine.linearFitHigh[ BPP.imageTypeIndex( this.imageType ) ] );
      this.ESD_OutliersControl.setValue( engine.ESD_Outliers[ BPP.imageTypeIndex( this.imageType ) ] );
      this.ESD_SignificanceControl.setValue( engine.ESD_Significance[ BPP.imageTypeIndex( this.imageType ) ] );
      this.RCR_Limit.setValue( engine.RCR_Limit[ BPP.imageTypeIndex( this.imageType ) ] );

      this.percentileLowControl.enabled = false;
      this.percentileHighControl.enabled = false;
      this.sigmaLowControl.enabled = false;
      this.sigmaHighControl.enabled = false;
      this.linearFitLowControl.enabled = false;
      this.linearFitHighControl.enabled = false;
      this.ESD_OutliersControl.enabled = false;
      this.ESD_SignificanceControl.enabled = false;
      this.RCR_Limit.enabled = false;

      switch ( engine.rejection[ BPP.imageTypeIndex( this.imageType ) ] )
      {
         case ImageIntegration.PercentileClip:
            this.percentileLowControl.enabled = true;
            this.percentileHighControl.enabled = true;
            break;

         case ImageIntegration.WinsorizedSigmaClip:
            this.sigmaLowControl.enabled = true;
            this.sigmaHighControl.enabled = true;
            break;

         case ImageIntegration.LinearFit:
            this.linearFitLowControl.enabled = true;
            this.linearFitHighControl.enabled = true;
            break;

         case ImageIntegration.Rejection_ESD:
            this.ESD_OutliersControl.enabled = true;
            this.ESD_SignificanceControl.enabled = true;
            break;

         case ImageIntegration.Rejection_RCR:
            this.RCR_Limit.enabled = true;
            break;

         case BPP.REJECTION_AUTO:
            this.percentileLowControl.enabled = true;
            this.percentileHighControl.enabled = true;
            this.sigmaLowControl.enabled = true;
            this.sigmaHighControl.enabled = true;
            this.linearFitLowControl.enabled = true;
            this.linearFitHighControl.enabled = true;
            this.ESD_OutliersControl.enabled = true;
            this.ESD_SignificanceControl.enabled = true;
            this.RCR_Limit.enabled = true;
            break;
      }

      if ( this.imageType == ImageType.Flat )
      {
         this.flatLargeScaleRejectionCheckBox.checked = engine.flatsLargeScaleRejection;
         this.flatLargeScaleRejectionLayersSpinBox.value = engine.flatsLargeScaleRejectionLayers;
         this.flatLargeScaleRejectionGrowthSpinBox.value = engine.flatsLargeScaleRejectionGrowth;

         let enabled = engine.rejection[ BPP.imageTypeIndex( this.imageType ) ] != ImageIntegration.NoRejection;
         this.flatLargeScaleRejectionCheckBox.enabled = enabled;
         this.flatLargeScaleRejectionLayersSpinBox.enabled = enabled && engine.flatsLargeScaleRejection;
         this.flatLargeScaleRejectionGrowthSpinBox.enabled = enabled && engine.flatsLargeScaleRejection;
      }

      if ( this.imageType == ImageType.Light )
      {
         this.lightLargeScaleRejectionHighCheckBox.checked = engine.lightsLargeScaleRejectionHigh;
         this.lightLargeScaleRejectionLayersHighSpinBox.value = engine.lightsLargeScaleRejectionLayersHigh;
         this.lightLargeScaleRejectionGrowthHighSpinBox.value = engine.lightsLargeScaleRejectionGrowthHigh;
         this.lightLargeScaleRejectionLowCheckBox.checked = engine.lightsLargeScaleRejectionLow;
         this.lightLargeScaleRejectionLayersLowSpinBox.value = engine.lightsLargeScaleRejectionLayersLow;
         this.lightLargeScaleRejectionGrowthLowSpinBox.value = engine.lightsLargeScaleRejectionGrowthLow;

         let enabled = engine.rejection[ BPP.imageTypeIndex( this.imageType ) ] != ImageIntegration.NoRejection;
         this.lightLargeScaleRejectionHighCheckBox.enabled = enabled;
         this.lightLargeScaleRejectionLowCheckBox.enabled = enabled;
         this.lightLargeScaleRejectionLayersHighSpinBox.enabled = enabled && engine.lightsLargeScaleRejectionHigh;
         this.lightLargeScaleRejectionGrowthHighSpinBox.enabled = enabled && engine.lightsLargeScaleRejectionHigh;
         this.lightLargeScaleRejectionLayersLowSpinBox.enabled = enabled && engine.lightsLargeScaleRejectionLow;
         this.lightLargeScaleRejectionGrowthLowSpinBox.enabled = enabled && engine.lightsLargeScaleRejectionLow;
      }
   };

   this.reset = function()
   {
      engine.defaults.imageIntegration( this.imageType );
      this.updateControls();
   };
   }
}

// ----------------------------------------------------------------------------

var LinearPatternSubtractionControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Linear Defects Correction", parent, false, true );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.linearPatternSubtraction = checked;
      this.dialog.updateControls();
   };

   //

   let toolTipRejectionLimit =
      "<p>Threshold to perform a bright pixel rejection in each column or "
      + "row of the small-scale component image. This will ensure a precise "
      + "calculation of statistics in each column or row, without a bias "
      + "toward bright pixels. The value is expressed in sigma units with "
      + "respect to background noise.</p>";

   this.rejectionLimit_Label = new Label( this );
   this.rejectionLimit_Label.text = "Rejection limit:";
   this.rejectionLimit_Label.toolTip = toolTipRejectionLimit;
   this.rejectionLimit_Label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.rejectionLimit_Label.minWidth = this.dialog.labelWidth1;

   this.rejectionLimit_SpinBox = new SpinBox( this );
   this.rejectionLimit_SpinBox.setRange( 0, 15 );
   this.rejectionLimit_SpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
   this.rejectionLimit_SpinBox.toolTip = toolTipRejectionLimit
   this.rejectionLimit_SpinBox.onValueUpdated = function( value )
   {
      engine.linearPatternSubtractionRejectionLimit = value;
   };

   this.rejectionLimit_Sizer = new HorizontalSizer;
   this.rejectionLimit_Sizer.spacing = 4;
   this.rejectionLimit_Sizer.add( this.rejectionLimit_Label );
   this.rejectionLimit_Sizer.add( this.rejectionLimit_SpinBox );
   this.rejectionLimit_Sizer.addStretch();

   //

   let toolTipMode = "<p>The type of correction to be applied.</p>";

   this.mode_Label = new Label( this );
   this.mode_Label.text = "Correction type:";
   this.mode_Label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.mode_Label.minWidth = this.dialog.labelWidth1;

   this.mode_ComboBox = new ComboBox( this );
   this.mode_ComboBox.addItem( "Columns" );
   this.mode_ComboBox.addItem( "Rows" );
   this.mode_ComboBox.addItem( "Columns and rows" );
   this.mode_ComboBox.toolTip = toolTipMode;
   this.mode_ComboBox.onItemSelected = function( item )
   {
      engine.linearPatternSubtractionMode = item;
   };

   this.mode_sizer = new HorizontalSizer;
   this.mode_sizer.spacing = 4;
   this.mode_sizer.add( this.mode_Label );
   this.mode_sizer.add( this.mode_ComboBox, 100 );
   this.mode_sizer.addStretch();

   //

   this.add( this.rejectionLimit_Sizer );
   this.add( this.mode_sizer );

   this.updateControls = () =>
   {
      if ( engine.linearPatternSubtraction )
         this.activate();
      else
         this.deactivate();

      this.rejectionLimit_SpinBox.value = engine.linearPatternSubtractionRejectionLimit;
      this.mode_ComboBox.currentItem = engine.linearPatternSubtractionMode;
   };
   }
}

// ----------------------------------------------------------------------------

var SubframesWeightsEditControl = class extends ParametersControl
{
   constructor( parent, expand )
   {
      super( "Weighting Formula Parameters", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ );

   this.presetsLabel = new Label( this );
   this.presetsLabel.text = "Preset:";
   this.presetsLabel.minWidth = this.dialog.labelWidth1 / 1.4;
   this.presetsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.presetsComboBox = new ComboBox( this );
   this.presetsComboBox.addItem( "" );
   this.presetsComboBox.addItem( "Nebula" );
   this.presetsComboBox.addItem( "Galaxy" );
   this.presetsComboBox.addItem( "Cluster" );
   this.presetsComboBox.addItem( "By number of stars" );
   this.presetsComboBox.addItem( "Photometric" );
   this.presetsComboBox.addItem( "Photometric SNR" );
   this.presetsComboBox.currentItem = engine.subframeWeightingPreset;
   this.presetsComboBox.onItemSelected = ( item ) =>
   {
      engine.subframeWeightingPreset = item;
      // update sliders
      switch ( item )
      {
         case 1: // Nebula
            engine.FWHMWeight = 5;
            engine.eccentricityWeight = 10;
            engine.starsWeight = 0;
            engine.PSFSignalWeight = 0;
            engine.PSFSNRWeight = 0;
            engine.SNRWeight = 20;
            engine.pedestal = 65;
            break;
         case 2: // Galaxy
            engine.FWHMWeight = 20;
            engine.eccentricityWeight = 15;
            engine.starsWeight = 0;
            engine.PSFSignalWeight = 0;
            engine.PSFSNRWeight = 0;
            engine.SNRWeight = 25;
            engine.pedestal = 40;
            break;
         case 3: // Cluster
            engine.FWHMWeight = 35;
            engine.eccentricityWeight = 35;
            engine.starsWeight = 0;
            engine.PSFSignalWeight = 0;
            engine.PSFSNRWeight = 0;
            engine.SNRWeight = 20;
            engine.pedestal = 10;
            break;
         case 4: // By number of stars
            engine.FWHMWeight = 0;
            engine.eccentricityWeight = 0;
            engine.starsWeight = 40;
            engine.PSFSignalWeight = 0;
            engine.PSFSNRWeight = 0;
            engine.SNRWeight = 0;
            engine.pedestal = 60;
            break;
         case 5: // Photometric
            engine.FWHMWeight = 0;
            engine.eccentricityWeight = 0;
            engine.starsWeight = 0;
            engine.PSFSignalWeight = 100;
            engine.PSFSNRWeight = 0;
            engine.SNRWeight = 0;
            engine.pedestal = 0;
            break;
         case 6: // Photometric SNR
            engine.FWHMWeight = 0;
            engine.eccentricityWeight = 0;
            engine.starsWeight = 0;
            engine.PSFSignalWeight = 0;
            engine.PSFSNRWeight = 100;
            engine.SNRWeight = 0;
            engine.pedestal = 0;
            break;
      }
      this.updateControls();
   };

   this.presetsSizer = new HorizontalSizer;
   this.presetsSizer.spacing = 4;
   this.presetsSizer.add( this.presetsLabel );
   this.presetsSizer.add( this.presetsComboBox, 100 );

   //

   this.FWHMControl = new NumericControl( this );
   this.FWHMControl.label.text = "FWHM:";
   this.FWHMControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.FWHMControl.setRange( 0, 100 );
   this.FWHMControl.slider.setRange( 0, 100 );
   this.FWHMControl.slider.scaledMinWidth = 1;
   this.FWHMControl.setPrecision( 0 );
   this.FWHMControl.toolTip = "<p>Weight contribution of the FWHM.</p>";

   this.FWHMControl.onValueUpdated = ( value ) =>
   {
      engine.FWHMWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.FWHMSizer = new HorizontalSizer;
   this.FWHMSizer.spacing = 4;
   this.FWHMSizer.add( this.FWHMControl );

   //

   this.eccentricityControl = new NumericControl( this );
   this.eccentricityControl.label.text = "Eccentricity:";
   this.eccentricityControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.eccentricityControl.setRange( 0, 100 );
   this.eccentricityControl.slider.setRange( 0, 100 );
   this.eccentricityControl.slider.scaledMinWidth = 1;
   this.eccentricityControl.setPrecision( 0 );
   this.eccentricityControl.toolTip = "<p>Weight contribution of the stars eccentricity.</p>";

   this.eccentricityControl.onValueUpdated = ( value ) =>
   {
      engine.eccentricityWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.eccentricitySizer = new HorizontalSizer;
   this.eccentricitySizer.spacing = 4;
   this.eccentricitySizer.add( this.eccentricityControl );

   //

   this.SNRControl = new NumericControl( this );
   this.SNRControl.label.text = "SNR:";
   this.SNRControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.SNRControl.setRange( 0, 100 );
   this.SNRControl.slider.setRange( 0, 100 );
   this.SNRControl.slider.scaledMinWidth = 1;
   this.SNRControl.setPrecision( 0 );
   this.SNRControl.toolTip = "<p>Weight contribution of the SNR.</p>";

   this.SNRControl.onValueUpdated = ( value ) =>
   {
      engine.SNRWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.SNRSizer = new HorizontalSizer;
   this.SNRSizer.spacing = 4;
   this.SNRSizer.add( this.SNRControl );

   //

   this.starsControl = new NumericControl( this );
   this.starsControl.label.text = "Number of stars:";
   this.starsControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.starsControl.setRange( 0, 100 );
   this.starsControl.slider.setRange( 0, 100 );
   this.starsControl.slider.scaledMinWidth = 1;
   this.starsControl.setPrecision( 0 );
   this.starsControl.toolTip = "<p>Weight contribution of the number of stars.</p>";

   this.starsControl.onValueUpdated = ( value ) =>
   {
      engine.starsWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.starsSizer = new HorizontalSizer;
   this.starsSizer.spacing = 4;
   this.starsSizer.add( this.starsControl );

   //

   this.PSFSignalControl = new NumericControl( this );
   this.PSFSignalControl.label.text = "PSF Signal Weight:";
   this.PSFSignalControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.PSFSignalControl.setRange( 0, 100 );
   this.PSFSignalControl.slider.setRange( 0, 100 );
   this.PSFSignalControl.slider.scaledMinWidth = 1;
   this.PSFSignalControl.setPrecision( 0 );
   this.PSFSignalControl.toolTip = "<p>Weight contribution of the PSF Signal Weight estimator.</p>";

   this.PSFSignalControl.onValueUpdated = ( value ) =>
   {
      engine.PSFSignalWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.PSFSignalSizer = new HorizontalSizer;
   this.PSFSignalSizer.spacing = 4;
   this.PSFSignalSizer.add( this.PSFSignalControl );

   //

   this.PSFSNRControl = new NumericControl( this );
   this.PSFSNRControl.label.text = "PSF SNR Weight:";
   this.PSFSNRControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.PSFSNRControl.setRange( 0, 100 );
   this.PSFSNRControl.slider.setRange( 0, 100 );
   this.PSFSNRControl.slider.scaledMinWidth = 1;
   this.PSFSNRControl.setPrecision( 0 );

   this.PSFSNRControl.toolTip = "<p>Weight contribution of the PSF SNR estimator.</p>";
   this.PSFSNRControl.onValueUpdated = ( value ) =>
   {
      engine.PSFSNRWeight = value;
      engine.subframeWeightingPreset = 0;
      this.updateControls();
   };

   this.PSFSNRSizer = new HorizontalSizer;
   this.PSFSNRSizer.spacing = 4;
   this.PSFSNRSizer.add( this.PSFSNRControl );

   //

   this.pedestalControl = new NumericControl( this );
   this.pedestalControl.label.text = "Pedestal:";
   this.pedestalControl.label.minWidth = this.dialog.labelWidth1 / 1.4;
   this.pedestalControl.setRange( 0, 100 );
   this.pedestalControl.slider.setRange( 0, 100 );
   this.pedestalControl.slider.scaledMinWidth = 1;
   this.pedestalControl.setPrecision( 0 );
   this.pedestalControl.toolTip = "<p>Pedestal added to the weight.</p>";
   this.pedestalControl.onValueUpdated = ( value ) =>
   {
      engine.pedestal = value;
      this.updateControls();
   };
   this.pedestalSizer = new HorizontalSizer;
   this.pedestalSizer.spacing = 4;
   this.pedestalSizer.add( this.pedestalControl );

   //

   this.add( this.presetsSizer );
   this.add( this.FWHMSizer );
   this.add( this.eccentricitySizer );
   this.add( this.SNRSizer );
   this.add( this.starsSizer );
   this.add( this.PSFSignalSizer );
   this.add( this.PSFSNRSizer );
   this.add( this.pedestalSizer );

   //

   this.updateControls = function()
   {
      this.presetsComboBox.currentItem = engine.subframeWeightingPreset;
      this.FWHMControl.setValue( engine.FWHMWeight );
      this.eccentricityControl.setValue( engine.eccentricityWeight );
      this.starsControl.setValue( engine.starsWeight );
      this.PSFSignalControl.setValue( engine.PSFSignalWeight );
      this.PSFSNRControl.setValue( engine.PSFSNRWeight );
      this.SNRControl.setValue( engine.SNRWeight );
      this.pedestalControl.setValue( engine.pedestal );
   };

   this.reset = function()
   {
      engine.defaults.customFormulaWeights();
      this.updateControls();
   };

   this.updateControls();
   }
}

// ----------------------------------------------------------------------------

var ImageRegistrationControl = class extends ParametersControl
{
   constructor( parent, expand )
   {
      super( "Image Registration", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ );

   this.pixelInterpolationLabel = new Label( this );
   this.pixelInterpolationLabel.text = "Pixel interpolation:";
   this.pixelInterpolationLabel.minWidth = this.dialog.labelWidth1;
   this.pixelInterpolationLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.pixelInterpolationComboBox = new ComboBox( this );
   this.pixelInterpolationComboBox.addItem( "Nearest Neighbor" );
   this.pixelInterpolationComboBox.addItem( "Bilinear" );
   this.pixelInterpolationComboBox.addItem( "Bicubic Spline" );
   this.pixelInterpolationComboBox.addItem( "Bicubic B-Spline" );
   this.pixelInterpolationComboBox.addItem( "Lanczos-3" );
   this.pixelInterpolationComboBox.addItem( "Lanczos-4" );
   this.pixelInterpolationComboBox.addItem( "Lanczos-5" );
   this.pixelInterpolationComboBox.addItem( "Mitchell-Netravali Filter" );
   this.pixelInterpolationComboBox.addItem( "Catmul-Rom Spline Filter" );
   this.pixelInterpolationComboBox.addItem( "Cubic B-Spline Filter" );
   this.pixelInterpolationComboBox.addItem( "Auto" );
   this.pixelInterpolationComboBox.currentItem = engine.pixelInterpolation;
   this.pixelInterpolationComboBox.toolTip = "<p>Pixel interpolation algorithm</p>"
      + "<p>The default automatic mode will select the following interpolation algorithms as a function of the "
      + "rescaling involved in the registration geometrical transformation:</p>"
      + "<ul>"
      + "<li>Cubic B-spline filter interpolation when the scaling factor is under 0.25 approximately.</li>"
      + "<li>Mitchell-Netravali filter interpolation for scaling factors between 0.6 and 0.25 approx.</li>"
      + "<li>Lanczos-3 interpolation in the rest of cases: from moderate size reductions to no rescaling or "
      + "rescaling up.</li>"
      + "</ul>"
      + "<p><b>Lanczos</b> is, in general, the best interpolation algorithm for image registration of linear "
      + "images when no large scale changes are required. Lanczos has excellent detail preservation and subpixel "
      + "registration performance with minimal generation of aliasing effects. Its main drawback is generation of "
      + "undershoot (ringing) artifacts, but this problem can be fixed in most cases with the implemented "
      + "<i>clamping</i> mechanism (see the <i>clamping threshold</i> parameter below).</p>"
      + "<p><b>Bicubic spline</b> is an excellent interpolation algorithm in terms of accuracy and execution "
      + "speed. As Lanczos interpolation, bicubic spline generates ringing artifacts, but the implemented clamping "
      + "mechanism can usually fix most of them. The main problem with bicubic spline is generation of aliasing "
      + "effects, such as moire patterns, which can be problematic with noisy images, especially on sky background "
      + "areas. This is one of the reasons why Lanczos is in general the preferred option.</p>"
      + "<p><b>Bilinear interpolation</b> can be useful to register low SNR linear images, in the rare cases where "
      + "Lanczos and bicubic spline interpolation generates too strong oscillations between noisy pixels that can't "
      + "be avoided completely with the clamping feature. Bilinear interpolation has no ringing artifacts, but it "
      + "generates strong aliasing patterns on noisy areas and provides less accurate results than Lanczos and "
      + "bicubic spline.</p>"
      + "<p><b>Cubic filter interpolations</b>, such as Mitchell-Netravali, Catmull-Rom spline and cubic B-spline, "
      + "provide higher smoothness and subsampling accuracy that can be necessary when the registration transformation "
      + "involves relatively strong size reductions.</p>"
      + "<p><b>Nearest neighbor</b> is the simplest possible pixel interpolation method. It always produces the "
      + "worst results, especially in terms of registration accuracy (no subpixel registration is possible), and "
      + "discontinuities due to the simplistic interpolation scheme. However, in absence of scaling and rotation "
      + "nearest neighbor preserves the original noise distribution in the registered images, a property that can "
      + "be useful in some image analysis applications.</p>";

   this.pixelInterpolationComboBox.onItemSelected = function( item )
   {
      engine.pixelInterpolation = item;
   };

   this.pixelInterpolationSizer = new HorizontalSizer;
   this.pixelInterpolationSizer.spacing = 4;
   this.pixelInterpolationSizer.add( this.pixelInterpolationLabel );
   this.pixelInterpolationSizer.add( this.pixelInterpolationComboBox );
   this.pixelInterpolationSizer.addStretch();

   //

   this.clampingThresholdControl = new NumericControl( this );
   this.clampingThresholdControl.label.text = "Clamping threshold:";
   this.clampingThresholdControl.label.minWidth = this.dialog.labelWidth1;
   this.clampingThresholdControl.setRange( 0, 1 );
   this.clampingThresholdControl.slider.setRange( 0, 1000 );
   this.clampingThresholdControl.slider.scaledMinWidth = 200;
   this.clampingThresholdControl.setPrecision( 2 );
   this.clampingThresholdControl.setValue( engine.clampingThreshold );
   this.clampingThresholdControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.clampingThresholdControl.toolTip = "<p>Clamping threshold for the bicubic spline and Lanczos interpolation algorithms.</p>"
      + "<p>The main drawback of the Lanczos and bicubic spline interpolation algorithms is generation of strong "
      + "undershoot (ringing) artifacts. This is caused by negative lobes of the interpolation functions falling "
      + "over high-contrast edges and isolated bright pixels. This usually happens with linear data, such as raw CCD "
      + "and DSLR images, and rarely with nonlinear or stretched images.</p>"
      + "<p>In the current PixInsight/PCL implementations of these algorithms we have included a clamping mechanism that "
      + "prevents negative interpolated values and ringing artifacts for most images. This parameter represents a "
      + "threshold value to trigger interpolation clamping. A lower threshold leads to a more aggressive deringing effect; "
      + "however, too low of a clamping threshold can degrade interpolation performance, especially in terms of aliasing "
      + "and detail preservation.</p>";
   this.clampingThresholdControl.onValueUpdated = function( value )
   {
      engine.clampingThreshold = value;
   };

   //

   this.maxStarsLabel = new Label( this );
   this.maxStarsLabel.text = "Maximum stars:";
   this.maxStarsLabel.minWidth = this.dialog.labelWidth1;
   this.maxStarsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.maxStarsSpinBox = new SpinBox( this );
   this.maxStarsSpinBox.minValue = 0; // <Auto>
   this.maxStarsSpinBox.maxValue = 262144;
   this.maxStarsSpinBox.minimumValueText = "<Auto>";
   this.maxStarsSpinBox.toolTip = "<p>Maximum number of stars allowed for image registration.</p>"
      + "<p>With the default &lt;Auto&gt; option, the WBPP script does not impose any restrictions on the maximum number of stars "
      + "used by the StarAlignment process for image registration. This means that the 2000 brightest stars will be used for each image "
      + "by default. If you want to speed up the image registration process you can specify a smaller amount for this parameter, "
      + "say 500 stars for example, which can be sufficient to achieve an accurate alignment for similar images without differential "
      + "distortions.</p>"
      + "<p>If your images suffer from field distortions and the data set includes significantly displaced or rotated frames, such "
      + "as frames affected by meridian flips for example, then you should enable the distortion correction option. In such case this "
      + "parameter will be ignored and the StarAlignment tool will select the required stars automatically.</p>";
   this.maxStarsSpinBox.onValueUpdated = function( value )
   {
      engine.maxStars = value;
   };

   this.maxStarsSizer = new HorizontalSizer;
   this.maxStarsSizer.spacing = 4;
   this.maxStarsSizer.add( this.maxStarsLabel );
   this.maxStarsSizer.add( this.maxStarsSpinBox );
   this.maxStarsSizer.addStretch();

   //

   this.distortionCorrectionCheckBox = new CheckBox( this );
   this.distortionCorrectionCheckBox.text = "Distortion correction";
   this.distortionCorrectionCheckBox.toolTip = "<p>Check this option to enable StarAlignment's arbitrary distortion correction "
      + "algorithm.</p>"
      + "<p>Each pixel in a registered image is interpolated from a set of source image pixels mapped by inverse projection. "
      + "This parameter defines the general method used to compute source pixel coordinates.</p>"
      + "<p>If distortion correction is disabled, a linear transformation (either a projective transformation or <i>homography</i> "
      + "or a rigid transformation, will be used to compute source pixel coordinates. This is appropriate for general image "
      + "registration tasks with significant overlapping between registered images without differential distortion. This is the "
      + "default option.</p>"
      + "<p>When distortion correction is enabled, two-dimensional surface splines will be used with second-order polyharmonic "
      + "radial basis functions (also known as <i>thin plates</i>) to compute a distortion model and interpolate source pixel "
      + "coordinates. Surface splines provide extremely adaptable registration models for registering images affected by "
      + "differential distortions. Differential distortions arise frequently in the registration of significantly displaced or "
      + "rotated frames, as usually happens when some frames have been acquired with the field rotated due to a meridian flip.</p>"
      + "<p>The standard StarAlignment process provides many more options and parameters to control how distortion corrections are "
      + "calculated and applied. Although the limited control provided in the WBPP script is more than sufficient in most practical "
      + "cases, in really complex cases, you may need to turn off image registration in this script and perform the registration "
      + "task manually after calibration/demosaicing.</p>";
   this.distortionCorrectionCheckBox.__parentControl__ = this;
   this.distortionCorrectionCheckBox.onCheck = function( checked )
   {
      engine.distortionCorrection = checked;
      this.__parentControl__.updateControls();
   };

   this.distortionCorrectionSizer = new HorizontalSizer;
   this.distortionCorrectionSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.distortionCorrectionSizer.add( this.distortionCorrectionCheckBox );
   this.distortionCorrectionSizer.addStretch();

   //

   this.maxSplinePointsLabel = new Label( this );
   this.maxSplinePointsLabel.text = "Maximum spline points:";
   this.maxSplinePointsLabel.minWidth = this.dialog.labelWidth1;
   this.maxSplinePointsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.maxSplinePointsSpinBox = new SpinBox( this );
   this.maxSplinePointsSpinBox.minValue = 1000;
   this.maxSplinePointsSpinBox.maxValue = 25000;
   this.maxSplinePointsSpinBox.toolTip = "<p>This parameter specifies the maximum number of control points allowed for the "
      + "generation of surface splines using DDM-RBF algorithms.</p>"
      + "<p>When the <i>distortion correction</i> option is selected, this parameter allows specifying the maximum number of control "
      + "points (or reference stars) that will be used (after surface simplification) to generate the 2-D interpolating/approximating "
      + "surface splines that model coordinate transformations for image registration. Thanks to PixInsight's efficient DDM-RBF "
      + "implementation, this parameter can be specified from 1000 to 25000 control points. The default value is 4000 points, which is "
      + "sufficient for the vast majority of practical applications.</p>"
      + "<p>Increase this parameter to achieve more accuracy at the expense of more computational work. Remember that DDM-RBF surface "
      + "spline generation has O(n^2) time complexity, so be careful when you increase the value of this parameter above its default "
      + "value because it can severely impact execution performance.</p>";
   this.maxSplinePointsSpinBox.onValueUpdated = function( value )
   {
      engine.maxSplinePoints = value;
   };

   this.maxSplinePointsSizer = new HorizontalSizer;
   this.maxSplinePointsSizer.spacing = 4;
   this.maxSplinePointsSizer.add( this.maxSplinePointsLabel );
   this.maxSplinePointsSizer.add( this.maxSplinePointsSpinBox );
   this.maxSplinePointsSizer.addStretch();

   //

   this.rigidTransformationsCheckBox = new CheckBox( this );
   this.rigidTransformationsCheckBox.text = "Rigid transformations";
   this.rigidTransformationsCheckBox.toolTip = "<p>Compute rigid transformations instead of projective "
      + "transformations (or homographies).</p>"
      + "<p>A two-dimensional rigid transformation, or Euclidean transformation, preserves the Euclidean "
      + "distance between every pair of transformed points. Rigid transformations may include rotations, "
      + "translations and reflections in any order.</p>"
      + "<p>A two-dimensional projective transformation, or homography, is a line-preserving geometric "
      + "transformation between two sets of points in the plane. Homographies can model translations, "
      + "rotations, reflections, scale changes and shearing in any order.</p>"
      + "<p>By default, StarAlignment computes homographies to model complex linear image registration "
      + "transformations with the maximum accuracy. However, with only 3 degrees of freedom, rigid "
      + "transformations can be more robust and faster, requiring fewer RANSAC iterations even when dealing with "
      + "a high proportion of outliers in the initial set of putative star pair matches.</p>"
      + "<p>Note that this option is relevant for all registration models, including linear and nonlinear models "
      + "with arbitrary distortion correction using surface splines. In the latter case, a linear model is always "
      + "necessary to build an initial registration transformation before modeling distortions.</p>";
   this.rigidTransformationsCheckBox.__parentControl__ = this;
   this.rigidTransformationsCheckBox.onCheck = function( checked )
   {
      engine.rigidTransformations = checked;
      this.__parentControl__.updateControls();
   };

   this.rigidTransformationsSizer = new HorizontalSizer;
   this.rigidTransformationsSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.rigidTransformationsSizer.add( this.rigidTransformationsCheckBox );
   this.rigidTransformationsSizer.addStretch();

   //

   this.structureLayersLabel = new Label( this );
   this.structureLayersLabel.text = "Detection scales:";
   this.structureLayersLabel.minWidth = this.dialog.labelWidth1;
   this.structureLayersLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.structureLayersSpinBox = new SpinBox( this );
   this.structureLayersSpinBox.minValue = 1;
   this.structureLayersSpinBox.maxValue = 8;
   this.structureLayersSpinBox.toolTip = "<p>Number of wavelet layers used for structure detection.</p>"
      + "<p>With more wavelet layers, larger stars (and perhaps also some nonstellar objects) will be detected.</p>";
   this.structureLayersSpinBox.onValueUpdated = function( value )
   {
      engine.structureLayers = value;
   };

   this.structureLayersSizer = new HorizontalSizer;
   this.structureLayersSizer.spacing = 4;
   this.structureLayersSizer.add( this.structureLayersLabel );
   this.structureLayersSizer.add( this.structureLayersSpinBox );
   this.structureLayersSizer.addStretch();

   //

   this.minStructureSizeLabel = new Label( this );
   this.minStructureSizeLabel.text = "Minimum structure size:";
   this.minStructureSizeLabel.minWidth = this.dialog.labelWidth1;
   this.minStructureSizeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.minStructureSizeSpinBox = new SpinBox( this );
   this.minStructureSizeSpinBox.minValue = 0;
   this.minStructureSizeSpinBox.maxValue = 65535;
   this.minStructureSizeSpinBox.minimumValueText = "<Auto>";
   this.minStructureSizeSpinBox.toolTip = "<p>Minimum size of a detectable star structure in square pixels.</p>"
      + "<p>This parameter can be used to prevent the detection of small and bright image artifacts wrongly as stars. "
      + "This can be useful to work with uncalibrated or poorly calibrated data, especially demosaiced CFA frames where "
      + "uncorrected hot pixels have generated large bright artifacts that cannot be removed with a median filter "
      + "(i.e., the <i>Hot pixel removal</i> parameter), or for rejection of cosmic rays.</p>"
      + "<p>This parameter can be used in three ways:</p>"
      + "<p><b>* Automatic mode.</b> A zero value enables an adaptive algorithm to find an optimal minimum structure "
      + "size using statistical analysis techniques. This is the default option.</p>"
      + "<p><b>* Disabled.</b> A value of one turns off minimum structure size rejection since no detectable star can "
      + "be represented by less than one pixel.</p>"
      + "<p><b>* Literal value.</b> A value &gt; 1 forces using the specified minimum structure size in square pixels.</p>";
   this.minStructureSizeSpinBox.onValueUpdated = function( value )
   {
      engine.minStructureSize = value;
   };

   this.minStructureSizeSizer = new HorizontalSizer;
   this.minStructureSizeSizer.spacing = 4;
   this.minStructureSizeSizer.add( this.minStructureSizeLabel );
   this.minStructureSizeSizer.add( this.minStructureSizeSpinBox );
   this.minStructureSizeSizer.addStretch();

   //

   this.hotPixelFilterRadiusLabel = new Label( this );
   this.hotPixelFilterRadiusLabel.text = "Hot pixel removal:";
   this.hotPixelFilterRadiusLabel.minWidth = this.dialog.labelWidth1;
   this.hotPixelFilterRadiusLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.hotPixelFilterRadiusSpinBox = new SpinBox( this );
   this.hotPixelFilterRadiusSpinBox.minValue = 0;
   this.hotPixelFilterRadiusSpinBox.maxValue = 2;
   this.hotPixelFilterRadiusSpinBox.minimumValueText = "<Disabled>";
   this.hotPixelFilterRadiusSpinBox.toolTip = "<p>Size of the hot pixel removal filter.</p>"
      + "<p>This is the radius in pixels of a median filter applied by the star detector before the structure "
      + "detection phase. A median filter is very efficient to remove <i>hot pixels</i>. Hot pixels will be "
      + "identified as false stars, and if present in large amounts, can prevent a valid image registration.</p>"
      + "<p>To disable hot pixel removal, set this parameter to zero.</p>";
   this.hotPixelFilterRadiusSpinBox.onValueUpdated = function( value )
   {
      engine.hotPixelFilterRadius = value;
   };

   this.hotPixelFilterRadiusSizer = new HorizontalSizer;
   this.hotPixelFilterRadiusSizer.spacing = 4;
   this.hotPixelFilterRadiusSizer.add( this.hotPixelFilterRadiusLabel );
   this.hotPixelFilterRadiusSizer.add( this.hotPixelFilterRadiusSpinBox );
   this.hotPixelFilterRadiusSizer.addStretch();

   //

   this.noiseReductionFilterRadiusLabel = new Label( this );
   this.noiseReductionFilterRadiusLabel.text = "Noise reduction:";
   this.noiseReductionFilterRadiusLabel.minWidth = this.dialog.labelWidth1;
   this.noiseReductionFilterRadiusLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

   this.noiseReductionFilterRadiusSpinBox = new SpinBox( this );
   this.noiseReductionFilterRadiusSpinBox.minValue = 0;
   this.noiseReductionFilterRadiusSpinBox.maxValue = 50;
   this.noiseReductionFilterRadiusSpinBox.minimumValueText = "<Disabled>";
   this.noiseReductionFilterRadiusSpinBox.toolTip = "<p>Size of the noise reduction filter.</p>"
      + "<p>This is the radius in pixels of a Gaussian convolution filter applied to the working image used for "
      + "calculation of star positions during the star detection phase. Use it only for very low SNR images, where "
      + "the star detector cannot find reliable stars with default parameters.</p>"
      + "<p>Be aware that noise reduction will modify star profiles and hence the way star positions are calculated, "
      + "resulting in a less accurate image registration. Under extreme low-SNR conditions, however, this is probably "
      + "better than working with the actual data anyway.</p>"
      + "<p>To disable noise reduction, set this parameter to zero.</p>";
   this.noiseReductionFilterRadiusSpinBox.onValueUpdated = function( value )
   {
      engine.noiseReductionFilterRadius = value;
   };

   this.noiseReductionFilterRadiusSizer = new HorizontalSizer;
   this.noiseReductionFilterRadiusSizer.spacing = 4;
   this.noiseReductionFilterRadiusSizer.add( this.noiseReductionFilterRadiusLabel );
   this.noiseReductionFilterRadiusSizer.add( this.noiseReductionFilterRadiusSpinBox );
   this.noiseReductionFilterRadiusSizer.addStretch();

   //

   this.sensitivityControl = new NumericControl( this );
   this.sensitivityControl.label.text = "Sensitivity:";
   this.sensitivityControl.label.minWidth = this.dialog.labelWidth1;
   this.sensitivityControl.setRange( 0, 1 );
   this.sensitivityControl.slider.setRange( 0, 100 );
   this.sensitivityControl.slider.scaledMinWidth = 200;
   this.sensitivityControl.setPrecision( 2 );
   this.sensitivityControl.setValue( engine.sensitivity );
   this.sensitivityControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.sensitivityControl.toolTip = "<p>Star detection sensitivity.</p>"
      + "<p>Internally, the sensitivity of the star detection algorithm is expressed in signal-to-noise ratio units with "
      + "respect to the evaluated dispersion of local background pixels for each detected structure. Given a source with "
      + "estimated brightness <i>s</i>, local background <i>b</i> and local background dispersion <i>n</i>, sensitivity "
      + "is the minimum value of (<i>s</i> - <i>b</i>)/<i>n</i> necessary to trigger star detection.</p>"
      + "<p>To isolate this interface from the internal implementation, this parameter is normalized to the [0,1] range, "
      + "where 0 and 1 represent minimum and maximum sensitivity, respectively. This abstraction allows us to change the "
      + "star detection engine without breaking dependent tools and processes.</p>"
      + "<p>Increase this parameter to favor detection of fainter stars. Decrease it to restrict detection to brighter "
      + "stars. The default value is 0.5. In general, you shouldn't need to change the default value of this parameter "
      + "under normal working conditions.</p>";
   this.sensitivityControl.onValueUpdated = function( value )
   {
      engine.sensitivity = value;
   };

   //

   this.peakResponseControl = new NumericControl( this );
   this.peakResponseControl.label.text = "Peak response:";
   this.peakResponseControl.label.minWidth = this.dialog.labelWidth1;
   this.peakResponseControl.setRange( 0, 1 );
   this.peakResponseControl.slider.setRange( 0, 100 );
   this.peakResponseControl.slider.scaledMinWidth = 200;
   this.peakResponseControl.setPrecision( 2 );
   this.peakResponseControl.setValue( engine.peakResponse );
   this.peakResponseControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.peakResponseControl.toolTip = "<p>Peak sensitivity of the star detection device.</p>"
      + "<p>Internally, the peak response property of the star detection algorithm is expressed in kurtosis units. For "
      + "each detected structure, kurtosis is evaluated from all significant pixels with values greater than the estimated "
      + "mean local background. Peak response is the minimum value of kurtosis necessary to trigger star detection.</p>"
      + "<p>To isolate this interface from the internal implementation, this parameter is normalized to the [0,1] range, "
      + "where 0 and 1 represent minimum and maximum peak response, respectively. This abstraction allows us to change the "
      + "star detection engine without breaking dependent tools and processes.</p>"
      + "<p>If you decrease this parameter, stars will need to have stronger (or more prominent) peaks to be detected. This "
      + "is useful to prevent detection of saturated stars, as well as small nonstellar features. By increasing this "
      + "parameter, the star detection algorithm will be more sensitive to <i>peakedness</i>, and hence more tolerant with "
      + "relatively flat image features. The default value is 0.5. In general, you shouldn't need to change the default "
      + "value of this parameter under normal working conditions.</p>";
   this.peakResponseControl.onValueUpdated = function( value )
   {
      engine.peakResponse = value;
   };

   //

   this.brightThresholdControl = new NumericControl( this );
   this.brightThresholdControl.label.text = "Bright threshold:";
   this.brightThresholdControl.label.minWidth = this.dialog.labelWidth1;
   this.brightThresholdControl.setRange( 1, 100 );
   this.brightThresholdControl.slider.setRange( 1, 100 );
   this.brightThresholdControl.slider.scaledMinWidth = 200;
   this.brightThresholdControl.setPrecision( 2 );
   this.brightThresholdControl.setValue( engine.brightThreshold );
   this.brightThresholdControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.brightThresholdControl.toolTip = "<p>Bright star detection threshold</p>"
      + "<p>Sources with measured SNR above this parameter in units of the minimum detection level (as defined by the "
      + "sensitivity parameter) will always be detected, even if their profiles are too flat for the current peak response. "
      + "This parameter allows us to force inclusion of relatively bright stars irrespective of their shapes, and also "
      + "provides finer control on the amount of detectable stars, along with the sensitivity parameter. The default value "
      + "is 3.0.</p>";
   this.brightThresholdControl.onValueUpdated = function( value )
   {
      engine.brightThreshold = value;
   };

   //

   this.maxStarDistortionControl = new NumericControl( this );
   this.maxStarDistortionControl.label.text = "Maximum distortion:";
   this.maxStarDistortionControl.label.minWidth = this.dialog.labelWidth1;
   this.maxStarDistortionControl.setRange( 0, 1 );
   this.maxStarDistortionControl.slider.setRange( 0, 100 );
   this.maxStarDistortionControl.slider.scaledMinWidth = 200;
   this.maxStarDistortionControl.setPrecision( 2 );
   this.maxStarDistortionControl.setValue( engine.maxStarDistortion );
   this.maxStarDistortionControl.edit.setFixedWidth( this.dialog.numericEditWidth );
   this.maxStarDistortionControl.toolTip = "<p>Maximum star distortion.</p>"
      + "<p>Internally, star distortion is evaluated in units of coverage of a square region circumscribed to each detected "
      + "structure. The coverage of a perfectly circular star is &pi;/4 (about 0.8). Lower values denote elongated or "
      + "irregular sources.</p>"
      + "<p>To isolate this interface from the internal implementation, this parameter is normalized to the [0,1] range, "
      + "where 0 and 1 represent minimum and maximum distortion, respectively. This abstraction allows us to change the "
      + "star detection engine without breaking dependent tools and processes.</p>"
      + "<p>Use this parameter, if necessary, to control inclusion of elongated stars, complex clusters of stars, and "
      + "nonstellar image features. The default value is 0.6. In general, you shouldn't need to change the default value of "
      + "this parameter under normal working conditions.</p>";
   this.maxStarDistortionControl.onValueUpdated = function( value )
   {
      engine.maxStarDistortion = value;
   };

   //

   this.allowClusteredSourcesCheckBox = new CheckBox( this );
   this.allowClusteredSourcesCheckBox.text = "Allow clustered sources";
   this.allowClusteredSourcesCheckBox.toolTip = "<p>If this parameter is disabled, a local maxima map will be generated to "
      + "identify and prevent detection of multiple sources that are too close to be separated as individual structures, such "
      + "as double and multiple stars. In general, sources with several local maxima pose difficulties for the determination of "
      + "accurate star positions.</p>"
      + "<p>If this parameter is enabled, non-separable multiple sources will be freely detectable as single objects. This can "
      + "be necessary in special cases where extreme high noise levels and/or distortion of stellar images caused by optical "
      + "aberrations limit the number of detectable sources excessively, preventing image registration.</p>"
      + "<p>The default state is disabled.</p>";
   this.allowClusteredSourcesCheckBox.onCheck = function( checked )
   {
      engine.allowClusteredSources = checked;
   };

   this.allowClusteredSourcesSizer = new HorizontalSizer;
   this.allowClusteredSourcesSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.allowClusteredSourcesSizer.add( this.allowClusteredSourcesCheckBox );
   this.allowClusteredSourcesSizer.addStretch();

   //

   this.useTriangleSimilarityCheckBox = new CheckBox( this );
   this.useTriangleSimilarityCheckBox.text = "Use triangle similarity";
   this.useTriangleSimilarityCheckBox.toolTip = "<p>If this option is checked, the image registration process will use "
      + "triangle similarity instead of polygonal descriptors for the star matching routine.</p>"
      + "<p>Polygonal descriptors are more robust and accurate, but cannot register images subject to specular transformations "
      + "(horizontal and vertical mirror). Triangle similarity works well under normal conditions and is able to register "
      + "mirrored images, so it is the default option in the WBPP script. If you need more control on image "
      + "registration parameters, check the <i>calibrate only</i> option and align your images manually after calibration.</p>";
   this.useTriangleSimilarityCheckBox.onCheck = function( checked )
   {
      engine.useTriangleSimilarity = checked;
   };

   this.useTriangleSimilaritySizer = new HorizontalSizer;
   this.useTriangleSimilaritySizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.useTriangleSimilaritySizer.add( this.useTriangleSimilarityCheckBox );
   this.useTriangleSimilaritySizer.addStretch();

   //

   this.add( this.pixelInterpolationSizer );
   this.add( this.clampingThresholdControl );
   this.add( this.maxStarsSizer );
   this.add( this.distortionCorrectionSizer );
   this.add( this.maxSplinePointsSizer );
   this.add( this.rigidTransformationsSizer );
   this.add( this.structureLayersSizer );
   this.add( this.minStructureSizeSizer );
   this.add( this.hotPixelFilterRadiusSizer );
   this.add( this.noiseReductionFilterRadiusSizer );
   this.add( this.sensitivityControl );
   this.add( this.peakResponseControl );
   this.add( this.brightThresholdControl );
   this.add( this.maxStarDistortionControl );
   this.add( this.allowClusteredSourcesSizer );
   this.add( this.useTriangleSimilaritySizer );

   this.updateControls = function()
   {
      this.pixelInterpolationComboBox.currentItem = engine.pixelInterpolation;
      this.clampingThresholdControl.setValue( engine.clampingThreshold );
      this.maxStarsSpinBox.value = engine.maxStars;
      this.maxStarsSpinBox.enabled = !engine.distortionCorrection;
      this.distortionCorrectionCheckBox.checked = engine.distortionCorrection;
      this.maxSplinePointsSpinBox.value = engine.maxSplinePoints;
      this.maxSplinePointsLabel.enabled = engine.distortionCorrection;
      this.maxSplinePointsSpinBox.enabled = engine.distortionCorrection;
      this.rigidTransformationsCheckBox.checked = engine.rigidTransformations;
      this.structureLayersSpinBox.value = engine.structureLayers;
      this.minStructureSizeSpinBox.value = engine.minStructureSize;
      this.hotPixelFilterRadiusSpinBox.value = engine.hotPixelFilterRadius;
      this.noiseReductionFilterRadiusSpinBox.value = engine.noiseReductionFilterRadius;
      this.sensitivityControl.setValue( engine.sensitivity );
      this.peakResponseControl.setValue( engine.peakResponse );
      this.brightThresholdControl.setValue( engine.brightThreshold );
      this.maxStarDistortionControl.setValue( engine.maxStarDistortion );
      this.allowClusteredSourcesCheckBox.checked = engine.allowClusteredSources;
      this.useTriangleSimilarityCheckBox.checked = engine.useTriangleSimilarity;
   };

   this.reset = function()
   {
      engine.defaults.imageRegistration();
      this.updateControls();
   };
   }
}

// ----------------------------------------------------------------------------

var LocalNormalizationControl = class extends ParametersControl
{
   constructor( parent, expand )
   {
      super( "Local Normalization", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ );

   let labelWidth = this.font.width( "Reference frame generation:" + "mm" );

   //

   this.generateCheckBox = new CheckBox( this );
   this.generateCheckBox.text = "Generate images";
   this.generateCheckBox.toolTip = "<p>If checked, normalized images will be generated along with normalization .xnml files.</p>"
      + "<p>Local normalization functions, stored in .xnml files, can be used by the ImageIntegration and DrizzleIntegration "
      + "processes for normalization in the pixel rejection and/or integration output tasks. This means that the normalization "
      + "functions can be applied internally by these processes, so writing normalized images to disk files is generally not "
      + "necessary. In addition, the ImageIntegration and DrizzleIntegration processes apply normalization functions internally "
      + "without any truncation or rescaling of the data, so the entire data set is always integrated without any loss or "
      + "artificial alteration when local normalization files are used.</p>"
      + "<p>Generation of normalized image files can be useful in very difficult cases, for example when the data set includes "
      + "strong and large artifacts, such as big plane trails. In these cases you may want to inspect locally normalized images "
      + "manually with analysis tools such as Blink.</p>";
   this.generateCheckBox.onCheck = ( checked ) =>
   {
      engine.localNormalizationGenerateImages = checked;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.addUnscaledSpacing( labelWidth + this.logicalPixelsToPhysical( 4 ) );
      sizer.add( this.generateCheckBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let referenceFrameGenerationToolTip = "<p>Available methods for automatic selection of the reference frame for local "
      + "normalization.</p>"
      + "<p>The <b>single best frame</b> method uses the one with the best values according to the specified "
      + "evaluation criteria as reference frame.</p>"
      + "<p>The <b>integration of best frames</b> method generates a reference frame with a higher SNR by integrating the best "
      + "frames (1/3 of the total) according to the specified evaluation criteria.</p>";

   this.referenceFrameGenerationLabel = new Label( this );
   this.referenceFrameGenerationLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.referenceFrameGenerationLabel.text = "Reference frame generation:";
   this.referenceFrameGenerationLabel.toolTip = referenceFrameGenerationToolTip;
   this.referenceFrameGenerationLabel.setFixedWidth( labelWidth );

   this.referenceFrameGenerationComboBox = new ComboBox( this );
   this.referenceFrameGenerationComboBox.addItem( "Single best frame" );
   this.referenceFrameGenerationComboBox.addItem( "Integration of best frames" );
   this.referenceFrameGenerationComboBox.toolTip = referenceFrameGenerationToolTip;
   this.referenceFrameGenerationComboBox.onItemSelected = ( item ) =>
   {
      engine.localNormalizationReferenceFrameGenerationMethod = item;
      if ( this.onReferenceFrameGenerationChange )
         this.onReferenceFrameGenerationChange();
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.referenceFrameGenerationLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.referenceFrameGenerationComboBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let maxIntegratedFramesToolTip = "<p>The maximum number of frames used to integrate the Local Normalization reference frame.</p>"
      + "<p>The number of integrated best frames is 1/3 of the total frames up to a maximum given by this value. "
      + "<p>Higher values may include more frames, lowering the noise and increasing the SNR in the reference frame. Lower values reduce the "
      + "possibility of including bad frames that could affect the normalization results.</p>"
      + "<p>Normally, you don't have to change this parameter, unless you "
      + "need to include more frames to gaurantee enough SNR in the reference frame, like the case when light frames have a very short "
      + "exposure time or the subject is very faint, or you need to reduce the risk of including bad frames due to the presence of a lot of "
      + "bad-quality frames in the data.</p>";

   this.maxIntegratedFramesLabel = new Label( this );
   this.maxIntegratedFramesLabel.text = "Maximum integrated frames:";
   this.maxIntegratedFramesLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.maxIntegratedFramesLabel.toolTip = maxIntegratedFramesToolTip;
   this.maxIntegratedFramesLabel.setFixedWidth( labelWidth );

   this.maxIntegratedFramesSpinBox = new SpinBox( this );
   this.maxIntegratedFramesSpinBox.minValue = BPP.Defaults.localnormalizationMinIntegratedFrames;
   this.maxIntegratedFramesSpinBox.maxValue = BPP.Defaults.localnormalizationMaxIntegratedFrames;
   this.maxIntegratedFramesSpinBox.toolTip = maxIntegratedFramesToolTip;
   this.maxIntegratedFramesSpinBox.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationMaxIntegratedFrames = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.maxIntegratedFramesLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.maxIntegratedFramesSpinBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let bestReferenceSelectionMethodToolTip = "<p>Evaluation criteria used to sort the frames when selecting or generating the local "
      + "normalization reference frame.</p>";

   this.bestReferenceFrameMethodLabel = new Label( this );
   this.bestReferenceFrameMethodLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.bestReferenceFrameMethodLabel.text = "Evaluation criteria:";
   this.bestReferenceFrameMethodLabel.toolTip = bestReferenceSelectionMethodToolTip;
   this.bestReferenceFrameMethodLabel.setFixedWidth( labelWidth );

   this.bestReferenceFrameMethodComboBox = new ComboBox( this );
   this.bestReferenceFrameMethodComboBox.addItem( "PSF Signal Weight" );
   this.bestReferenceFrameMethodComboBox.addItem( "PSF SNR" );
   this.bestReferenceFrameMethodComboBox.addItem( "M*" );
   this.bestReferenceFrameMethodComboBox.addItem( "Median" );
   this.bestReferenceFrameMethodComboBox.addItem( "Number of stars" );
   this.bestReferenceFrameMethodComboBox.toolTip = bestReferenceSelectionMethodToolTip;
   this.bestReferenceFrameMethodComboBox.onItemSelected = ( item ) =>
   {
      engine.localNormalizationBestReferenceSelectionMethod = item;
      if ( this.onEvaluationCriteriaChanged )
         this.onEvaluationCriteriaChanged();
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.bestReferenceFrameMethodLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.bestReferenceFrameMethodComboBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let scaleToolTip = "<p>LocalNormalization implements a multiscale normalization algorithm. This parameter adaptively controls "
      + "the size in pixels of the sampling scale for local image normalization by subdividing the major dimension of the image by a "
      + "fixed number of rows (or columns). The larger this parameter, the more locally adaptive the local "
      + "normalization function will be. Higher values tend to reproduce variations among small-scale structures in the reference image. "
      + "Smaller values tend to reproduce variations among large-scale structures.</p>"
      + "<p>To better understand the role of this parameter, suppose we applied the algorithm with a grid size that precisely corresponds "
      + " to the major dimension of the image, with a resulting scale of one pixel. The result "
      + "would be an exact copy of the reference image. On the other hand, if we applied the algorithm with a grid size of 1, the "
      + "resulting scale scale would be the size of the whole image. Consequently, the result would be a <i>global normalization</i>: a single linear "
      + "function would be applied to normalize the entire target image.</p>"
      + "<p>The default grid size is 4, which is quite appropriate for most deep-sky images. Suitable scales are generally in the "
      + "range from 2 to 8.</p>";

   this.gridSizeNumericControl = new NumericControl( this );
   this.gridSizeNumericControl.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.gridSizeNumericControl.label.text = "Grid size:";
   this.gridSizeNumericControl.label.setFixedWidth( labelWidth );
   this.gridSizeNumericControl.label.toolTip = scaleToolTip;
   this.gridSizeNumericControl.toolTip = scaleToolTip;
   this.gridSizeNumericControl.setRange( 3, 32 );
   this.gridSizeNumericControl.slider.setRange( 2, 31 );
   this.gridSizeNumericControl.slider.scaledMinWidth = 200;
   this.gridSizeNumericControl.setPrecision( 2 );
   this.gridSizeNumericControl.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationGridSize = value;
   }

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.gridSizeNumericControl );
      sizer.addSpacing( 20 );
      this.add( sizer );
   }

   //

   let methodToolTip = "<p>Available methods for evaluation of the global relative scale of the reference image with respect "
      + "to each normalization target image.</p>"
      + "<p>The <b>PSF flux evaluation</b> method detects stars in the images and fits a point spread function model to each detected "
      + "source. The fitted PSF parameters are then used to guide evaluation of the total flux of each source, and the fluxes of matched "
      + "pairs of stars in both images are used to compute a robust and precise scale factor. This method is usually the best choice for "
      + "normalization of deep-sky astronomical images where stars can be detected efficiently.</p>"
      + "<p>The <b>multiscale analysis</b> method uses wavelet transforms and morphological operations to isolate significant image "
      + "structures. The pixels gathered on the intersection between significant structures of the reference and target images are then "
      + "evaluated statistically to estimate the scale factor.</p>";

   this.methodLabel = new Label( this );
   this.methodLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.methodLabel.text = "Scale evaluation method:";
   this.methodLabel.toolTip = methodToolTip;
   this.methodLabel.setFixedWidth( labelWidth );

   this.methodComboBox = new ComboBox( this );
   this.methodComboBox.addItem( "PSF flux evaluation" );
   this.methodComboBox.addItem( "Multiscale analysis" );
   this.methodComboBox.toolTip = methodToolTip;
   this.methodComboBox.onItemSelected = ( item ) =>
   {
      engine.localNormalizationMethod = item;
      this.updateControls();
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.methodLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.methodComboBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let psfTypeToolTip = "<p>Point spread function type used for PSF fitting and photometry.</p>"
      + "<p>In all cases elliptical functions are fitted to detected star structures, and PSF sampling regions are "
      + "defined adaptively using a median stabilization algorithm.</p>"
      + "<p>When the <b>Auto</b> option is selected, a series of different PSFs will be fitted for each source, and "
      + "the fit that leads to the least absolute difference among function values and sampled pixel values will be "
      + "used for scale estimation. Currently the following functions are tested in this special automatic mode: "
      + "Moffat functions with <i>beta</i> shape parameters equal to 2.5, 4, 6 and 10.</p>"
      + "<p>The rest of options select a fixed PSF type for all detected sources, which improves execution times at "
      + "the cost of a less adaptive, and hence potentially less accurate, relative scale measurement process.</p>";

   this.psfTypeLabel = new Label( this );
   this.psfTypeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.psfTypeLabel.text = "PSF type:";
   this.psfTypeLabel.toolTip = psfTypeToolTip;
   this.psfTypeLabel.setFixedWidth( labelWidth );

   this.psfTypeComboBox = new ComboBox( this );
   this.psfTypeComboBox.addItem( "Gaussian​" );
   this.psfTypeComboBox.addItem( "Moffat beta = 1.5​" );
   this.psfTypeComboBox.addItem( "Moffat beta = 4​" );
   this.psfTypeComboBox.addItem( "Moffat beta = 6​" );
   this.psfTypeComboBox.addItem( "Moffat beta = 8​" );
   this.psfTypeComboBox.addItem( "Moffat beta = 10​" );
   this.psfTypeComboBox.addItem( "Auto​" );
   this.psfTypeComboBox.toolTip = psfTypeToolTip;
   this.psfTypeComboBox.onItemSelected = ( item ) =>
   {
      engine.localNormalizationPsfType = item;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.psfTypeLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.psfTypeComboBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let psfGrowthFactorTooltip = "<p>Growing factor for expansion/contraction of the PSF flux measurement region for "
      + "each source, in units of the Full Width at Tenth Maximum (FWTM).</p>"
      + "<p>The default value of this parameter is 1.0, meaning that flux is measured exclusively for pixels within the elliptical "
      + "region defined at one tenth of the fitted PSF maximum. Increasing this parameter can inprove accuracy of PSF flux "
      + "measurements for undersampled images, where PSF fitting uncertainty is relatively large. Decreasing it can be beneficial "
      + "in some cases working with very noisy data to restrict flux evaluation to star cores.</p>";

   this.psfGrowthFactorNumericControl = new NumericControl( this );
   this.psfGrowthFactorNumericControl.label.text = "Growth factor:";
   this.psfGrowthFactorNumericControl.label.setFixedWidth( labelWidth );
   this.psfGrowthFactorNumericControl.slider.setRange( 0, 250 );
   this.psfGrowthFactorNumericControl.setReal( true );
   this.psfGrowthFactorNumericControl.setRange( 0.5, 4.0 );
   this.psfGrowthFactorNumericControl.setPrecision( 2 );
   this.psfGrowthFactorNumericControl.toolTip = psfGrowthFactorTooltip;
   this.psfGrowthFactorNumericControl.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationPsfGrowth = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.psfGrowthFactorNumericControl );
      sizer.addSpacing( 20 );
      this.add( sizer );
   }

   //

   let psfMaxStarsToolTip = "<p>The maximum number of stars that can be measured to compute mean scale estimates.</p>"
      + "<p>PSF photometry will be performed for no more than the specified number of stars. The subset of measured stars will always start "
      + "at the beginning of the set of detected stars, sorted by the brightness in descending order</p>"
      + "<p>The default value imposes a generous limit of 24k stars. Limiting the number of photometrix samples can improve performance "
      + "for normalization of wide-field frames, where the number of detected stars can be very large. However, reducing the set of "
      + "measured sources too much will damage the accuracy of scale evaluation</p>";

   this.psfMaxStarsLabel = new Label( this );
   this.psfMaxStarsLabel.text = "Maximum stars:";
   this.psfMaxStarsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.psfMaxStarsLabel.toolTip = psfMaxStarsToolTip;
   this.psfMaxStarsLabel.setFixedWidth( labelWidth );

   this.psfMaxStarsSpinBox = new SpinBox( this );
   this.psfMaxStarsSpinBox.minValue = BPP.Defaults.localnormalizationPsfMinStars;
   this.psfMaxStarsSpinBox.maxValue = BPP.Defaults.localnormalizationPsfMaxStars;
   this.psfMaxStarsSpinBox.toolTip = psfMaxStarsToolTip;
   this.psfMaxStarsSpinBox.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationPsfMaxStars = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.psfMaxStarsLabel );
      sizer.addSpacing( 4 );
      sizer.add( this.psfMaxStarsSpinBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let psfMinSNRTooltip = "<p>Minimum signal-to-noise ratio of a detectable star.</p>"
      + "<p>Given a source with estimated brightness <i>s</i>, local background <i>b</i> and local background dispersion "
      + "<i>n</i>, SNR is evaluated as (<i>s</i> &ndash; <i>b</i>)/<i>n</i>. Stars with measured SNR below the value of this "
      + "parameter won't be used for relative scale evaluation.</p>"
      + "<p>This parameter allows limiting star detection to a subset of the brightest sources in the image adaptively. By "
      + "requiring relatively high SNR levels in the evaluated sources, the accuracy and robustness of the scale evaluation "
      + "process can be largely improved. The default value is 40, which is quite appropriate in most cases.</p>";

   this.psfMinSNREdit = new NumericEdit( this );
   this.psfMinSNREdit.label.text = "Minimum detection SNR:";
   this.psfMinSNREdit.label.setFixedWidth( labelWidth );
   this.psfMinSNREdit.setReal( true );
   this.psfMinSNREdit.setPrecision( 1 );
   this.psfMinSNREdit.setRange( 0, 1000 );
   this.psfMinSNREdit.toolTip = psfMinSNRTooltip;
   this.psfMinSNREdit.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationPsfMinSNR = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.psfMinSNREdit );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   this.psfAllowClusteredSourcesCheckBox = new CheckBox( this );
   this.psfAllowClusteredSourcesCheckBox.text = "Allow clustered sources";
   this.psfAllowClusteredSourcesCheckBox.toolTip = "<p>If this parameter is disabled, multiple sources that are too close to be "
      + "separated as individual structures, such as double and multiple stars, won't be detected for relative scale evaluation.</p>"
      + "<p>If this parameter is enabled, non-separable multiple sources will be freely detectable as single objects.</p>"
      + "<p>In general, sources with several local maxima pose difficulties for the determination of accurate star positions and PSF "
      + "parameters, although this is usually a minor problem for scale evaluation. For this reason this parameter is enabled by "
      + "default.</p>";
   this.psfAllowClusteredSourcesCheckBox.onCheck = ( checked ) =>
   {
      engine.localNormalizationPsfAllowClusteredSources = checked;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.addUnscaledSpacing( labelWidth + this.logicalPixelsToPhysical( 4 ) );
      sizer.add( this.psfAllowClusteredSourcesCheckBox );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let lowClippingLevelTooltip = "<p>Low clipping pixel sample value in the [0,1] range.</p>"
      + "<p>All pixels with values smaller than or equal to the value of this parameter will be replaced with statistically "
      + "plausible estimates, computed from nearby image regions.</p>"
      + "<p>Rejection of very low pixels is necessary to prevent generation of large-scale artifacts around large dark structures, "
      + "such as black borders generated by image registration. Under normal conditions you shouldn't need to change the default "
      + "value of this parameter (4.5&times;10<sup>-5</sup>). Increase it in the unlikely case that you detect dark artifacts "
      + "around black borders&mdash;which, at any rate, will always denote a defective image calibration that you should fix "
      + "before normalization.</p>";

   this.lowClippingLevelEdit = new NumericEdit( this );
   this.lowClippingLevelEdit.label.text = "Low clipping level:";
   this.lowClippingLevelEdit.label.setFixedWidth( labelWidth );
   this.lowClippingLevelEdit.setReal( true );
   this.lowClippingLevelEdit.enableScientificNotation( true );
   this.lowClippingLevelEdit.setPrecision( 2 );
   this.lowClippingLevelEdit.setRange( 0.0, 0.45 );
   this.lowClippingLevelEdit.edit.setFixedWidth( this.font.width( "0000000000" ) );
   this.lowClippingLevelEdit.toolTip = lowClippingLevelTooltip;
   this.lowClippingLevelEdit.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationLowClippingLevel = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.lowClippingLevelEdit );
      sizer.addStretch();
      this.add( sizer );
   }

   //

   let highClippingLevelTooltip = "<p>High clipping pixel sample value in the [0,1] range.</p>"
      + "<p>All pixels with values greater than or equal to the value of this parameter will be replaced with statistically "
      + "plausible estimates, computed from nearby image regions.</p>"
      + "<p>Rejection of saturated pixels is necessary to prevent generation of large-scale artifacts around large saturated "
      + "structures, such as bright stars, in local background models. Under normal conditions you shouldn't need to change the "
      + "default value of this parameter (0.85). Decrease it in the unlikely case that you detect dark artifacts around large "
      + "saturated objects.</p>";

   this.highClippingLevelNumericControl = new NumericControl( this );
   this.highClippingLevelNumericControl.label.text = "High clipping level:";
   this.highClippingLevelNumericControl.label.setFixedWidth( labelWidth );
   this.highClippingLevelNumericControl.slider.setRange( 0, 250 );
   this.highClippingLevelNumericControl.setReal( true );
   this.highClippingLevelNumericControl.setRange( 0.5, 1.0 );
   this.highClippingLevelNumericControl.setPrecision( 2 );
   this.highClippingLevelNumericControl.toolTip = highClippingLevelTooltip;
   this.highClippingLevelNumericControl.onValueUpdated = ( value ) =>
   {
      engine.localNormalizationHighClippingLevel = value;
   };

   {
      let sizer = new HorizontalSizer;
      sizer.add( this.highClippingLevelNumericControl );
      sizer.addSpacing( 20 );
      this.add( sizer );
   }

   //

   this.updateControls = function()
   {
      this.generateCheckBox.checked = engine.localNormalizationGenerateImages;
      this.methodComboBox.currentItem = engine.localNormalizationMethod;
      this.maxIntegratedFramesSpinBox.value = engine.localNormalizationMaxIntegratedFrames;
      this.bestReferenceFrameMethodComboBox.currentItem = engine.localNormalizationBestReferenceSelectionMethod;
      this.gridSizeNumericControl.setValue( engine.localNormalizationGridSize );
      this.referenceFrameGenerationComboBox.currentItem = engine.localNormalizationReferenceFrameGenerationMethod;
      this.psfTypeComboBox.currentItem = engine.localNormalizationPsfType;
      this.psfGrowthFactorNumericControl.setValue( engine.localNormalizationPsfGrowth );
      this.psfMaxStarsSpinBox.value = engine.localNormalizationPsfMaxStars;
      this.psfMinSNREdit.setValue( engine.localNormalizationPsfMinSNR );
      this.psfAllowClusteredSourcesCheckBox.checked = engine.localNormalizationPsfAllowClusteredSources;
      this.lowClippingLevelEdit.setValue( engine.localNormalizationLowClippingLevel );
      this.highClippingLevelNumericControl.setValue( engine.localNormalizationHighClippingLevel );

      let psfParametersEnabled = engine.localNormalizationMethod == BPP.LocalNormalizationMethod.PSFFlux;
      this.psfTypeComboBox.enabled = psfParametersEnabled;
      this.psfMaxStarsSpinBox.enabled = psfParametersEnabled;
   };

   this.reset = function()
   {
      engine.defaults.localNormalization();
      this.updateControls();
   };
   }
}

// ----------------------------------------------------------------------------

var LightsIntegrationControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Image Integration", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ ,
         false /*withReset*/ , true /*withSettings */ );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.integrate = checked;
      this.dialog.updateControls();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.imageIntegrationControl.makeVisible();
   };

   //

   this.autocropCheckBox = new CheckBox( this );
   this.autocropCheckBox.text = "Autocrop";
   this.autocropCheckBox.checked = engine.autocrop;
   this.autocropCheckBox.toolTip = "<p>If enabled, each generated master light will be automatically cropped.</p>"
      + "<p>The cropping region will be the largest rectangle fully included within each registered frame image.</p>";
   this.autocropCheckBox.onCheck = ( checked ) =>
   {
      engine.autocrop = checked;
      engine.rebuild();
      this.dialog.pipelinePanel.updateContent();
   };

   this.autocropSizer = new HorizontalSizer;
   this.autocropSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.autocropSizer.add( this.autocropCheckBox );

   //

   this.autoIntegrationModeBox = new CheckBox( this );
   this.autoIntegrationModeBox.text = "Automatic integration mode";
   this.autoIntegrationModeBox.checked = engine.autoIntegrationMode;
   this.autoIntegrationModeBox.toolTip = "<p>If enabled, when more than 150 light frames are added to a post-calibration group for the first time, "
      + "fast integration is automatically enabled for that group, unless the integration mode has already been manually set.</p>";
   this.autoIntegrationModeBox.onCheck = ( checked ) =>
   {
      engine.autoIntegrationMode = checked;
   };

   this.autoIntegrationModeSizer = new HorizontalSizer;
   this.autoIntegrationModeSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.autoIntegrationModeSizer.add( this.autoIntegrationModeBox );

   //

   this.add( this.autocropSizer );
   this.add( this.autoIntegrationModeSizer );

   this.updateControls = function()
   {
      if ( engine.integrate )
         this.activate();
      else
         this.deactivate();
      this.autocropCheckBox.checked = engine.autocrop;
      this.autocropCheckBox.enabled = engine.integrate;
      this.settingsButton.enabled = engine.integrate;
   };
   }
}

// ----------------------------------------------------------------------------

var SubframesWeightingControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Subframe Weighting", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ , false /* withReset*/ , true /* withSettings */ );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.subframeWeightingEnabled = checked;
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.subframesWeightingControl.updateControls();
      this.dialog.calibrationPanelPostProcess.updateContent();
      this.dialog.pipelinePanel.updateContent();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.subframesWeightsEditControl.makeVisible();
   };

   let subframesWeightsTooltip = "<p>Image weighting method.</p>"
      +

      "<p>The <b>PSF Signal Weight (PSFSW)</b> and <b>PSF SNR</b> algorithms are based on robust estimates of total and mean flux "
      + "computed by PSF photometry, as well as noise estimates computed using multiscale analysis techniques. These methods "
      + "are robust and accurate. PSFSW is a comprehensive image quality estimator, able to capture a wide variety of image quality "
      + "metrics including signal-to-noise ratio, source dimensions and background gradients. PSF SNR is a good choice to generate "
      + "image weights based on signal-to-noise ratio exclusively. The PSF Signal Weight method is currently the default option."
      +

      "<p>The <b>PSF Scale SNR (PSFSSNR)</b> method uses relative scale estimates computed by the LocalNormalization tool and stored "
      + "in local normalization data files (XNML format, .xnml extension), along with multiscale noise estimates, to compute image "
      + "weights exclusively based on relative signal-to-noise ratios. This method is excellent to maximize SNR in the integrated image. "
      + "PSFSSNR requires .xnml files correctly associated with all input images to retrieve relative scale estimates, and all .xnml "
      + "files should be generated with the same normalization reference image.</p>"
      +

      "<p>The <b>SNR Estimate</b> method uses statistical scale estimators and multiscale noise evaluation techniques to compute SNR estimates. "
      + "These estimates are applied to minimize mean squared error in the integrated result, which in theory transforms the average "
      + "combination process into a maximum likelihood estimator of deterministic signal. This method can lead to optimal results in "
      + "terms of SNR maximization, but has potential robustness problems that can also generate wrong results, so it must be used with "
      + "care by analyzing the data prior to integration, for example with the SubframeSelector tool.</p>"
      +

      "<p>The <b>Weighting Formula</b> method generates image weights accordingly to the relative weights assigned to FWHM, eccentricity, "
      + "SNR and number of stars, plus a custom pedestal and a possible combination of PSFSW and PSF SNR. Weights are saved into the image "
      + "as WBPPWGHT header key which will be used during the ImageIntegration process.</p>";

   this.subframesWeightsLabel = new Label( this );
   this.subframesWeightsLabel.text = "Weights: ";
   this.subframesWeightsLabel.minWidth = this.dialog.labelWidth1;
   this.subframesWeightsLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.subframesWeightsLabel.toolTip = subframesWeightsTooltip;

   this.subframesWeightsComboBox = new ComboBox( this );
   this.subframesWeightsComboBox.addItem( "PSF Signal Weight" );
   this.subframesWeightsComboBox.addItem( "PSF SNR" );
   this.subframesWeightsComboBox.addItem( "PSF Scale SNR" );
   this.subframesWeightsComboBox.addItem( "SNR Estimate" );
   this.subframesWeightsComboBox.addItem( "Weighting Formula" );
   this.subframesWeightsComboBox.toolTip = subframesWeightsTooltip;
   this.subframesWeightsComboBox.onItemSelected = function( itemIndex )
   {
      engine.subframesWeightsMethod = itemIndex;
      this.dialog.updateControls();
   };

   this.subframesWeightDataSizer = new HorizontalSizer;
   this.subframesWeightDataSizer.add( this.subframesWeightsLabel );
   this.subframesWeightDataSizer.addUnscaledSpacing( this.logicalPixelsToPhysical( 4 ) );
   this.subframesWeightDataSizer.add( this.subframesWeightsComboBox );
   this.subframesWeightDataSizer.addStretch();

   //

   this.add( this.subframesWeightDataSizer );

   this.updateControls = () =>
   {
      if ( engine.subframeWeightingEnabled )
         this.activate();
      else
         this.deactivate();
      this.subframesWeightsComboBox.currentItem = engine.subframesWeightsMethod;
      this.settingsButton.enabled = engine.subframeWeightingEnabled && engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.FORMULA;
   };
   }
}

// ----------------------------------------------------------------------------

var FrameSelectionControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Frame Selection", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ , false /* withReset*/ , true /* withSettings */ );

   this.onActivateStatusChanged = function( checked )
   {
      engine.frameSelectionEnabled = checked;
      this.dialog.updateControls();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.frameSelectionSettingsControl.makeVisible();
   };

   // Interactive mode checkbox
   let interactiveTooltip = "<p>When enabled, an interactive dialog will be shown during processing where you can "
      + "review frame metrics and manually select which frames to reject.</p>"
      + "<p>When disabled, frames will be automatically rejected based on the default criteria configured in Settings.</p>";

   this.interactiveCheckBox = new CheckBox( this );
   this.interactiveCheckBox.text = "Interactive";
   this.interactiveCheckBox.toolTip = interactiveTooltip;
   this.interactiveCheckBox.onCheck = function( checked )
   {
      engine.frameSelectionInteractive = checked;
      this.dialog.updateControls();
   };

   this.interactiveSizer = new HorizontalSizer;
   this.interactiveSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.interactiveSizer.add( this.interactiveCheckBox );
   this.interactiveSizer.addStretch();

   this.add( this.interactiveSizer );

   this.updateControls = () =>
   {
      if ( engine.frameSelectionEnabled )
         this.activate();
      else
         this.deactivate();
      this.interactiveCheckBox.checked = engine.frameSelectionInteractive;
      // Settings button is enabled when frames selection is enabled
      // (for configuring default rejection criteria used in non-interactive mode)
      this.settingsButton.enabled = engine.frameSelectionEnabled;
   };
   }
}

// ----------------------------------------------------------------------------

/**
 * Expanded control for configuring frame selection default rejection criteria.
 * Shown when the Settings button is clicked on FrameSelectionControl.
 */
var FrameSelectionSettingsControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Frame Selection Default Criteria", parent, true /*expand*/ , false /*deactivatable*/ ,
         false /*collapsable*/ , true /*withReset*/ , false /* withSettings */ );

   // Description label
   this.descriptionLabel = new Label( this );
   this.descriptionLabel.text = "<p>Configure the default rejection criteria applied when Interactive mode is disabled.</p>";
   this.descriptionLabel.useRichText = true;
   this.descriptionLabel.wordWrapping = true;

   // Filter panel (no title, no apply-to-all button)
   this.filterPanel = new WBPPFrameSelectionFiltersControl( this, false /* showTitle */ , false /* showApplyToAll */ );
   this.filterPanel.onFilterChanged = () =>
   {
      // Save configuration when any filter changes
      engine.frameSelectionDefaultConfig = this.filterPanel.getFilterConfigs();
   };

   this.add( this.descriptionLabel );
   this.contents.sizer.addSpacing( 8 );
   this.add( this.filterPanel );

   /**
    * Reset callback for the reset button
    */
   this.reset = () =>
   {
      this.filterPanel.reset();
      engine.defaults.frameSelectionFilters();
   };

   this.updateControls = () =>
   {
      if ( engine.frameSelectionDefaultConfig )
         this.filterPanel.setFilterConfigs( engine.frameSelectionDefaultConfig );
      else
         this.filterPanel.reset();
   };
   }
}

// ----------------------------------------------------------------------------

var LightsRegistrationControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Image Registration", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ ,
         false /* withReset*/ , true /* withSettings */ );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.imageRegistration = checked;
      this.dialog.updateControls();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.imageRegistrationControl.makeVisible();
   };

   //

   this.reuseReferenceFrameCheckBox = new CheckBox( this );
   this.reuseReferenceFrameCheckBox.text = "Reuse last reference frames";
   this.reuseReferenceFrameCheckBox.toolTip = "<p>When checked, the registration reference frame for each group "
      + "will remain the same as the one selected in the previous execution.</p>"
      + "<p>Keeping the reference frame from the previous execution is beneficial when adding new light frames to an existing WBPP "
      + "group to increase the total integration time. By ensuring the same reference frame is used for each group, WBPP can "
      + "utilize the previously cached files that are still on disk, avoiding the need to measure and align them again. "
      + "This way, only the new files will be measured and registered, preventing the need to reprocess the entire dataset.</p>";
   this.reuseReferenceFrameCheckBox.onCheck = function( checked )
   {
      engine.reuseLastReferenceFrames = checked;
      this.dialog.updateControls();
   };

   this.reuseReferenceFrameSolveSizer = new HorizontalSizer;
   this.reuseReferenceFrameSolveSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.reuseReferenceFrameSolveSizer.add( this.reuseReferenceFrameCheckBox );
   this.reuseReferenceFrameSolveSizer.addStretch();

   this.add( this.reuseReferenceFrameSolveSizer );

   //

   this.updateControls = function()
   {
      if ( engine.imageRegistration )
         this.activate();
      else
         this.deactivate();
      this.reuseReferenceFrameCheckBox.checked = engine.reuseLastReferenceFrames;
      this.settingsButton.enabled = engine.imageRegistration;
   };
   }
}

// ----------------------------------------------------------------------------

var AstrometricSolutionControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Astrometric Solution", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ ,
         false /*withReset*/ , true /*withSettings*/ );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.platesolve = checked;
      this.dialog.updateControls();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.imageSolverParametersControl.makeVisible();
   };

   //

   this.manualPlatesolveCheckBox = new CheckBox( this );
   this.manualPlatesolveCheckBox.text = "Interactive in case of failure";
   this.manualPlatesolveCheckBox.toolTip = "<p>If a reference frame cannot be solved automatically, WBPP interactively presents the "
      + "ImageSolver script interface, where solver parameters can be manually tuned.</p>";
   this.manualPlatesolveCheckBox.onCheck = function( checked )
   {
      engine.platesolveFallbackManual = checked;
      this.dialog.updateControls();
   };

   this.platesolveSizer = new HorizontalSizer;
   this.platesolveSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.platesolveSizer.add( this.manualPlatesolveCheckBox );
   this.platesolveSizer.addStretch();

   this.add( this.platesolveSizer );

   //

   this.updateControls = function()
   {
      if ( engine.platesolve )
         this.activate();
      else
         this.deactivate();
      this.manualPlatesolveCheckBox.checked = engine.platesolveFallbackManual;
      this.settingsButton.enabled = engine.platesolve;
   };
   }
}

// ----------------------------------------------------------------------------

var ImageSolverParametersControl = class extends ParametersControl
{
   constructor( parent, expand )
   {
      super( "Image Solver default parameters", parent, expand,
         false /*deactivatable*/ , false /*collapsable*/ , true /*withReset*/ , false /* withSettings*/ );

   let labelLength = this.font.width( "Focal distance:" + "M" );
   let spinBoxWidth = 7 * this.font.width( 'M' );

   // CoordsEditor
   this.coordsSizer = new HorizontalSizer;
   this.coordsSizer.spacing = 8;

   let coordinatesTooltip = "<p>Initial equatorial coordinates. Must be inside the image.</p>";
   this.coordsEditor = new CoordinatesEditor( this,
      new Point(
         ( engine.imageSolverRa != null ) ? engine.imageSolverRa : 0,
         ( engine.imageSolverDec != null ) ? engine.imageSolverDec : 0 ),
      labelLength, spinBoxWidth, coordinatesTooltip );
   this.coordsEditor.onChangeCallback = ( point ) =>
   {
      engine.imageSolverRa = point.x;
      engine.imageSolverDec = point.y;
   };
   this.coordsEditor.onChangeCallbackScope = this;

   this.searchButton = new PushButton( this );
   this.searchButton.text = "Search";
   this.searchButton.icon = this.scaledResource( ":/icons/find.png" );
   this.searchButton.onClick = () =>
   {
      let search = new SearchCoordinatesDialog( null, true, false );
      search.windowTitle = "Online Coordinate Search";
      if ( search.execute() )
      {
         let object = search.object;
         if ( !object )
            return;
         this.coordsEditor.SetCoords( object.posEq );
         engine.imageSolverRa = object.posEq.x;
         engine.imageSolverDec = object.posEq.y;
      }
   };

   this.coordsSizer.add( this.coordsEditor );
   this.coordsSizer.addStretch();
   this.coordsSizer.add( this.searchButton );

   //

   this.dateTimeEditor = new DateTimeEditor( this, engine.imageSolverObservationTime, labelLength, spinBoxWidth );
   this.dateTimeEditor.onJDChanged = ( jd ) =>
   {
      engine.imageSolverObservationTime = jd;
   };

   //

   this.focalLabel = new Label( this );
   this.focalLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.focalLabel.text = "Focal distance:";
   this.focalLabel.setFixedWidth( labelLength );

   this.focalEdit = new Edit( this );
   this.focalEdit.text = format( "%g", engine.imageSolverFocalLength );
   this.focalEdit.toolTip = "<p>Effective focal length of the optical system in millimeters.</p>"
      + "<p>It doesn't need to be the exact value, but it should not be more than a 50% off"
      + "&mdash;the closer the better.</p>";
   this.focalEdit.setFixedWidth( spinBoxWidth );
   this.focalEdit.onEditCompleted = () =>
   {
      let fl = parseFloat( this.focalEdit.text );
      if ( !isNaN( fl ) )
         engine.imageSolverFocalLength = fl;

      this.updateControls();
   };

   this.focalmmLabel = new Label( this );
   this.focalmmLabel.text = "mm";
   this.focalmmLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;

   this.focalSizer = new HorizontalSizer;
   this.focalSizer.spacing = 4;
   this.focalSizer.add( this.focalLabel );
   this.focalSizer.add( this.focalEdit );
   this.focalSizer.add( this.focalmmLabel );
   this.focalSizer.addStretch();

   //

   this.pixelSizeLabel = new Label( this );
   this.pixelSizeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.pixelSizeLabel.text = "Pixel size:";
   this.pixelSizeLabel.setFixedWidth( labelLength );

   this.pixelSizeEdit = new Edit( this );
   this.pixelSizeEdit.toolTip = "<p>Pixel size in micrometers. "
      + "The image is assumed to have square pixels.</p>"
      + "<p>This pixel size value is the <i>effective</i> pixel size, which is the physical pixel size multiplied by the image binning.</p>";
   this.pixelSizeEdit.setFixedWidth( spinBoxWidth );
   this.pixelSizeEdit.onEditCompleted = () =>
   {
      let ps = parseFloat( this.pixelSizeEdit.text );
      if ( !isNaN( ps ) )
         engine.imageSolverPixelSize = ps;

      this.updateControls();
   };

   this.pixelSizemmLabel = new Label( this );
   this.pixelSizemmLabel.text = "\u03BCm";
   this.pixelSizemmLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;

   this.pixelSizeSizer = new HorizontalSizer;
   this.pixelSizeSizer.spacing = 4;
   this.pixelSizeSizer.add( this.pixelSizeLabel );
   this.pixelSizeSizer.add( this.pixelSizeEdit );
   this.pixelSizeSizer.add( this.pixelSizemmLabel );
   this.pixelSizeSizer.addStretch();

   //

   this.forceCheckBox = new CheckBox( this );
   this.forceCheckBox.text = "Force values";
   this.forceCheckBox.toolTip = "<p>If checked, all default parameters will be used regardless the metadata stored in the image.</p>";
   this.forceCheckBox.onCheck = ( checked ) =>
   {
      engine.imageSolverForceDefaults = checked;
      this.updateControls();
   };

   this.forceSizer = new HorizontalSizer;
   this.forceSizer.addUnscaledSpacing( labelLength );
   this.forceSizer.addSpacing( 4 );
   this.forceSizer.add( this.forceCheckBox );
   this.forceSizer.addStretch();

   //

   this.add( this.coordsSizer );
   if ( this.dateTimeEditor )
      this.add( this.dateTimeEditor );
   this.add( this.focalSizer );
   this.add( this.pixelSizeSizer );
   this.add( this.forceSizer );

   this.updateControls = function()
   {
      if ( this.coordsEditor )
         this.coordsEditor.SetCoords( new Point( engine.imageSolverRa, engine.imageSolverDec ) );
      if ( this.dateTimeEditor )
         this.dateTimeEditor.JD = engine.imageSolverObservationTime;
      this.focalEdit.text = format( "%i", engine.imageSolverFocalLength );
      this.pixelSizeEdit.text = format( "%g", engine.imageSolverPixelSize );
      this.forceCheckBox.checked = engine.imageSolverForceDefaults;
   };

   this.reset = function()
   {
      engine.defaults.imageSolver();
      this.updateControls();
   };

   this.updateControls();
   }
}

// ----------------------------------------------------------------------------

var LightsNormalizationControl = class extends ParametersControl
{
   constructor( parent )
   {
      super( "Local Normalization", parent, false /*expand*/ , true /*deactivatable*/ , false /*collapsable*/ ,
         false /*withReset*/ , true /*withSettings*/ );

   //

   this.onActivateStatusChanged = function( checked )
   {
      engine.localNormalization = checked;
      this.dialog.updateControls();
   };

   this.settings = function()
   {
      let lightsPage = this.dialog.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightsPage.localNormalizationControl.makeVisible();
   };

   //

   this.interactiveModeCheckbox = new CheckBox( this );
   this.interactiveModeCheckbox.text = "Interactive";
   this.interactiveModeCheckbox.toolTip = "<p>Use the Local Normalization Selector graphical interface for inspection, "
      + "evaluation and selection of the subset of frames used to generate the local normalization reference image.</p>";
   this.interactiveModeCheckbox.onCheck = ( checked ) =>
   {
      engine.localNormalizationInteractiveMode = checked;
      this.dialog.updateControls();
   };

   this.interactiveModeSizer = new HorizontalSizer;
   this.interactiveModeSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.interactiveModeSizer.add( this.interactiveModeCheckbox )
   this.add( this.interactiveModeSizer );

   //

   this.reuseLNReferenceFramesCheckbox = new CheckBox( this );
   this.reuseLNReferenceFramesCheckbox.text = "Reuse last reference frames";
   this.reuseLNReferenceFramesCheckbox.toolTip = "<p>When checked, the local normalization reference frame for each group "
      + "will remain the same as the one selected or generated in the previous execution.</p>"
      + "<p>Keeping the reference frame from the previous execution is beneficial when adding new light frames to an existing WBPP "
      + "group to increase the total integration time. By ensuring the same reference frame is used for each group, WBPP can "
      + "utilize the previously cached files that are still on disk, avoiding the need to select or generate the local normalization "
      + "reference again. This way, only the new files will be measured and normalized, preventing the need to reprocess the entire "
      + "dataset.</p>";
   this.reuseLNReferenceFramesCheckbox.onCheck = ( checked ) =>
   {
      engine.reuseLastLNReferenceFrames = checked;
      this.dialog.updateControls();
   };

   this.reuseLNReferenceFramesSizer = new HorizontalSizer;
   this.reuseLNReferenceFramesSizer.addUnscaledSpacing( this.dialog.labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.reuseLNReferenceFramesSizer.add( this.reuseLNReferenceFramesCheckbox )
   this.add( this.reuseLNReferenceFramesSizer );

   //

   this.updateControls = function()
   {
      this.interactiveModeCheckbox.checked = engine.localNormalizationInteractiveMode;
      if ( engine.localNormalization )
         this.activate();
      else
         this.deactivate();
      this.reuseLNReferenceFramesCheckbox.checked = engine.reuseLastLNReferenceFrames;
      this.settingsButton.enabled = engine.localNormalization;
   };
   }
}

// ----------------------------------------------------------------------------

var FileControl = class extends Control
{
   constructor( parent, imageType )
   {
      if ( parent )
         super( parent );
      else
         super();

   this.treeBox = new StyledTreeBox( this );
   this.treeBox.multipleSelection = true;
   this.treeBox.numberOfColumns = 1;
   this.treeBox.headerVisible = false;
   this.treeBox.setScaledMinWidth( 250 );
   this.treeBox.setVariableWidth();
   this.treeBox.setMaxWidth( 8192 );

   //

   this.rightContainer = new Control( this );
   this.rightContainer.sizer = new VerticalSizer;
   let rightContainerSizer = this.rightContainer.sizer;

   //

   this.clearButton = new PushButton( this.rightContainer );
   this.clearButton.text = "Clear";
   this.clearButton.icon = this.scaledResource( ":/icons/clear.png" );
   this.clearButton.toolTip = "<p>Clear the current list of input files.</p>";
   this.clearButton.onClick = () =>
   {
      this.dialog.clearTab( imageType );
      this.dialog.updateControls();
   };

   this.removeSelectedButton = new PushButton( this.rightContainer );
   this.removeSelectedButton.text = "Remove Selected";
   this.removeSelectedButton.icon = this.scaledResource( ":/icons/clear.png" );
   this.removeSelectedButton.toolTip = "<p>Remove selected items in the current list of input files.</p>";
   this.removeSelectedButton.onClick = () =>
   {
      let tree = this.dialog.tabBox.pageControlByIndex( this.dialog.tabBox.currentPageIndex ).treeBox;
      let selected = tree.selectedNodes;
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      // in the first step we only remove the selecgted file items
      // in the second step we remove selected groups
      for ( let step = 0; step < 2; ++step )
         for ( let i = 0; i < selected.length; ++i )
         {
            let node = selected[ i ];
            if ( step == 0 )
            {
               if ( node.nodeData_type == "FileItem" )
               {
                  // mark the file item as to be removed
                  groups[ node.nodeData_groupIndex ].fileItems[ node.nodeData_itemIndex ].__purged__ = true;
               }
            }
            else
            {
               if ( node.nodeData_type == "FrameGroup" )
               {
                  // mark children groups as to be removed
                  node.nodeData_indexes.forEach( i =>
                  {
                     groups[ i ].__purged__ = true;
                  } );
               }
            }
         }
      this.dialog.updateControls();
   };

   this.invertSelectionButton = new PushButton( this.rightContainer );
   this.invertSelectionButton.text = "Invert Selection";
   this.invertSelectionButton.icon = this.scaledResource( ":/icons/select-invert.png" );
   this.invertSelectionButton.toolTip = "<p>Invert selected items in the current list of input files.</p>";
   this.invertSelectionButton.onClick = () =>
   {
      function invertNodeSelection( node )
      {
         node.selected = !node.selected;
         for ( let i = 0; i < node.numberOfChildren; ++i )
            invertNodeSelection( node.child( i ) );
      }

      let tree = this.dialog.tabBox.pageControlByIndex( this.dialog.tabBox.currentPageIndex ).treeBox;
      for ( let i = 0; i < tree.numberOfChildren; ++i )
         invertNodeSelection( tree.child( i ) );
   };

   this.buttonsSizer = new( engine.fastMode ? VerticalSizer : HorizontalSizer );
   this.buttonsSizer.spacing = 6;
   this.buttonsSizer.add( this.clearButton );
   this.buttonsSizer.add( this.removeSelectedButton );
   // for light frames enable the show astrometric data checkbox
   if ( imageType == ImageType.Light )
   {
      this.showAstrometricInfoButton = new PushButton( this.rightContainer );
      this.showAstrometricInfoButton.toolTip = "<p>Shows or hide the astrometric information of each light frame.</p>";
      this.showAstrometricInfoButton.icon = this.scaledResource( ":/planets/orbit.png" );
      this.showAstrometricInfoButton.onClick = function()
      {
         engine.showAstrometricInfo = !engine.showAstrometricInfo;
         this.dialog.updateControls();
      }
      this.buttonsSizer.add( this.showAstrometricInfoButton );
   }
   this.buttonsSizer.addStretch();
   this.buttonsSizer.add( this.invertSelectionButton );
   rightContainerSizer.add( this.buttonsSizer );
   if ( !engine.fastMode )
      rightContainerSizer.addStretch();

   switch ( imageType )
   {
      case ImageType.Bias:

         this.biasOverscanControl = new BiasOverscanControl( this.rightContainer );
         this.biasOverscanControl.onCollapse = ( collapsed ) =>
         {
            engine.GUIBiasPageOverscanControlCollapsed = collapsed;
         }
         this.overscanControl = new OverscanControl( this.rightContainer, true /*expand*/ );
         this.imageIntegrationControl = new ImageIntegrationControl( this.rightContainer, ImageType.Bias );
         this.imageIntegrationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUIBiasPageImageIntegrationControlCollapsed = collapsed;
         }

         //

         if ( engine.fastMode )
            rightContainerSizer.addSpacing( 16 );
         rightContainerSizer.add( this.biasOverscanControl );
         rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.overscanControl );
         rightContainerSizer.add( this.imageIntegrationControl );

         if ( engine.fastMode )
         {
            rightContainerSizer.addStretch();

            this.imageIntegrationControl.visible = false;
            this.imageIntegrationControl.__alwaysHidden__ = true;
         }

         break;

      case ImageType.Dark:

         this.darkOptimizationThresholdControl = new NumericControl( this.rightContainer );
         this.darkOptimizationThresholdControl.label.text = "Optimization threshold:";
         this.darkOptimizationThresholdControl.label.minWidth = this.dialog.labelWidth1
            + this.dialog.logicalPixelsToPhysical( 6 ); // + integration control margin
         this.darkOptimizationThresholdControl.setRange( 0, 10 );
         this.darkOptimizationThresholdControl.slider.setRange( 0, 200 );
         this.darkOptimizationThresholdControl.setPrecision( 4 );
         this.darkOptimizationThresholdControl.toolTip = "<p>Lower bound for the set of dark optimization pixels, "
            + "measured in sigma units from the median.</p>"
            + "<p>This parameter defines the set of dark frame pixels that will be used to compute dark optimization "
            + "factors adaptively. By restricting this set to relatively bright pixels, the optimization process can "
            + "be more robust to readout noise present in the master bias and dark frames. Increase this parameter to "
            + "remove more dark pixels from the optimization set.</p>";
         this.darkOptimizationThresholdControl.onValueUpdated = function( value )
         {
            engine.darkOptimizationLow = value;
         };

         //

         this.darkExposureToleranceLabel = new Label( this.rightContainer );
         this.darkExposureToleranceLabel.text = "Exposure tolerance:";
         if ( !engine.fastMode )
            this.darkExposureToleranceLabel.minWidth = this.dialog.labelWidth1
            + this.dialog.logicalPixelsToPhysical( 6 ); // + integration control margin
         this.darkExposureToleranceLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;

         this.darkExposureToleranceSpinBox = new SpinBox( this.rightContainer );
         this.darkExposureToleranceSpinBox.minValue = 0;
         this.darkExposureToleranceSpinBox.maxValue = 600;
         this.darkExposureToleranceSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
         this.darkExposureToleranceSpinBox.toolTip = "<p>Dark frames with exposure times differing less than this value "
            + "(in seconds) will be grouped together.</p>";
         this.darkExposureToleranceSpinBox.onValueUpdated = ( value ) =>
         {
            engine.darkExposureTolerance = value;
            engine.rebuild();
            this.dialog.refreshTreeBoxes();
         };

         // manually add the exposure tolerance to the right controls parameter control list in orde to hide it automatically when
         // an expandable control is expanded. The main logic is handled in ParametersControl function.
         this.rightContainer.parameterControls = [ this.darkExposureToleranceLabel, this.darkExposureToleranceSpinBox ];

         this.darkExposureToleranceSizer = new HorizontalSizer;
         this.darkExposureToleranceSizer.spacing = 4;
         this.darkExposureToleranceSizer.add( this.darkExposureToleranceLabel );
         this.darkExposureToleranceSizer.add( this.darkExposureToleranceSpinBox );
         this.darkExposureToleranceSizer.addStretch();

         //

         this.imageIntegrationControl = new ImageIntegrationControl( this.rightContainer, ImageType.Dark );
         this.imageIntegrationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUIDarkPageImageIntegrationControlCollapsed = collapsed;
         }

         //
         if ( engine.fastMode )
            rightContainerSizer.addSpacing( 16 );
         rightContainerSizer.add( this.darkOptimizationThresholdControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 4 );
         rightContainerSizer.add( this.darkExposureToleranceSizer );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.imageIntegrationControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 4 );

         if ( engine.fastMode )
         {
            rightContainerSizer.addStretch();

            this.darkOptimizationThresholdControl.visible = false;
            this.darkOptimizationThresholdControl.__alwaysHidden__ = true;

            this.imageIntegrationControl.visible = false;
            this.imageIntegrationControl.__alwaysHidden__ = true;
         }

         break;

      case ImageType.Flat:

         this.imageIntegrationControl = new ImageIntegrationControl( this.rightContainer, ImageType.Flat );
         this.imageIntegrationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUIFlatPageImageIntegrationControlCollapsed = collapsed;
         }
         rightContainerSizer.add( this.imageIntegrationControl );
         if ( engine.fastMode )
         {
            rightContainerSizer.addStretch();

            this.imageIntegrationControl.visible = false;
            this.imageIntegrationControl.__alwaysHidden__ = true;
         }

         break;

      case ImageType.Light:

         let labelWidth2 = this.font.width( "Calibration exposure tolerance:" + "M" );

         let lightExposureToleranceTooltip = "<p>Light frames with exposure times differing less than this value "
            + "(in seconds) will be grouped together during the calibration step.</p>";

         this.lightExposureToleranceLabel = new Label( this.rightContainer );
         this.lightExposureToleranceLabel.text = "Calibration exposure tolerance:";
         this.lightExposureToleranceLabel.setFixedWidth( labelWidth2 );
         this.lightExposureToleranceLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
         this.lightExposureToleranceLabel.toolTip = lightExposureToleranceTooltip;

         this.lightExposureToleranceSpinBox = new SpinBox( this.rightContainer );
         this.lightExposureToleranceSpinBox.minValue = 0;
         this.lightExposureToleranceSpinBox.maxValue = 3600;
         this.lightExposureToleranceSpinBox.setFixedWidth( this.dialog.numericEditWidth + this.logicalPixelsToPhysical( 16 ) );
         this.lightExposureToleranceSpinBox.toolTip = lightExposureToleranceTooltip;
         this.lightExposureToleranceSpinBox.onValueUpdated = ( value ) =>
         {
            engine.lightExposureTolerance = value;
            engine.rebuild();
            this.dialog.refreshTreeBoxes();
         };

         // manually add the exposure tolerance to the right controls parameter control list in orde to hide it automatically when
         // an expandable control is expanded. The main logic is handled in ParametersControl function.
         this.rightContainer.parameterControls = [ this.lightExposureToleranceLabel, this.lightExposureToleranceSpinBox ];

         this.calibrationExposureToleranceSizer = new HorizontalSizer;
         this.calibrationExposureToleranceSizer.spacing = 4;
         this.calibrationExposureToleranceSizer.add( this.lightExposureToleranceLabel );
         this.calibrationExposureToleranceSizer.add( this.lightExposureToleranceSpinBox );
         this.calibrationExposureToleranceSizer.addStretch();

         this.linearPatternSubtractionControl = new LinearPatternSubtractionControl( this.rightContainer );
         this.linearPatternSubtractionControl.setActivatableCheckboxTooltip( "<p>Enable or disable the linear pattern "
            + "detection and correction task.</p>" );
         this.linearPatternSubtractionControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageLPSControlCollapsed = collapsed;
         };

         this.subframesWeightingControl = new SubframesWeightingControl( this.rightContainer );
         this.subframesWeightingControl.setActivatableCheckboxTooltip( "<p>Enable or disable the frames weighting. "
            + "If frames weighting is disabled, the frames will be equally weighted.</p>" );
         this.subframesWeightingControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageSubframeWeightingControlCollapsed = collapsed;
         };
         this.subframesWeightsEditControl = new SubframesWeightsEditControl( this.rightContainer, true /*expand*/ );

         this.frameSelectionControl = new FrameSelectionControl( this.rightContainer );
         this.frameSelectionControl.setActivatableCheckboxTooltip( "<p>Enable or disable frame selection. "
            + "When enabled, frames can be reviewed and selected based on quality metrics.</p>" );
         this.frameSelectionControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageFrameSelectionControlCollapsed = collapsed;
         };
         this.frameSelectionSettingsControl = new FrameSelectionSettingsControl( this.rightContainer );

         this.lightsRegistrationControl = new LightsRegistrationControl( this.rightContainer );
         this.lightsRegistrationControl.setActivatableCheckboxTooltip( "<p>Enable or disable image registration.</p>" );
         this.lightsRegistrationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageRegistrationControlCollapsed = collapsed;
         };
         this.imageRegistrationControl = new ImageRegistrationControl( this.rightContainer, true /*expand*/ );

         let platesolveTooltip = "<p>When this option is enabled, WBPP attempts to plate solve each registration reference frame "
            + "and propagates the astrometric solution to the corresponding registered frames.</p>"
            + "<p>To find a valid astrometric solution, the images must include valid metadata. At a minimum the following items "
            + "must be available:</p>"
            + "<ul>"
            + "<li>The approximate right ascension and declination coordinates of the image center (RA and DEC keywords).<br/></li>"
            + "<li>The pixel size (XPIXSZ keyword).<br/></li>"
            + "<li>The binning factor (BINNING or XBINNING keywords &mdash; optional, assuming binning 1 if missing).<br/></li>"
            + "<li>The effective optical focal length (FOCALLEN keyword).</li>"
            + "</ul></p>";
         this.platesolveControl = new AstrometricSolutionControl( this.rightContainer );
         this.platesolveControl.setActivatableCheckboxTooltip( platesolveTooltip );
         this.platesolveControl.onCollapse = ( collapsed ) =>
         {
            engine.GUIPlatesolveControlCollapsed = collapsed;
         };
         this.imageSolverParametersControl = new ImageSolverParametersControl( this.rightContainer, true /* expand */ );

         this.lightsNormalizationControl = new LightsNormalizationControl( this.rightContainer );
         this.lightsNormalizationControl.setActivatableCheckboxTooltip( "<p>Enable or disable local normalization.</p>" );
         this.lightsNormalizationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageNormalizationControlCollapsed = collapsed;
         };
         this.localNormalizationControl = new LocalNormalizationControl( this.rightContainer, true );

         this.lightsIntegrationControl = new LightsIntegrationControl( this.rightContainer );
         this.lightsIntegrationControl.setActivatableCheckboxTooltip( "<p>Enable or disable image integration.</p>" );
         this.lightsIntegrationControl.onCollapse = ( collapsed ) =>
         {
            engine.GUILightPageIntegrationControlCollapsed = collapsed;
         };
         this.imageIntegrationControl = new ImageIntegrationControl( this.rightContainer, ImageType.Light, true /*expand*/ );

         if ( engine.fastMode )
            rightContainerSizer.addSpacing( 16 );
         rightContainerSizer.add( this.calibrationExposureToleranceSizer );

         if ( engine.fastMode )
         {
            let fastIntegrationPlateSolveToolTip =
               "<p>When this option is enabled and the master light has the required metadata, namely:</p>"
               + "<ul>"
               + "<li>Observation time,</li>"
               + "<li>Approximate equatorial coordinates of the image center,</li>"
               + "<li>Focal length,</li>"
               + "<li>Pixel size,</li>"
               + "</ul>"
               + "<p>" + engine.title + " will compute the astrometric solution of the master light.</p>";

            this.fastIntegrationPlateSolveLabel = new Label( this.rightContainer );
            this.fastIntegrationPlateSolveLabel.text = "Astrometric solution:";
            this.fastIntegrationPlateSolveLabel.setFixedWidth( labelWidth2 );
            this.fastIntegrationPlateSolveLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
            this.fastIntegrationPlateSolveLabel.toolTip = fastIntegrationPlateSolveToolTip;

            this.fastIntegrationPlateSolveCheckBox = new CheckBox( this.rightContainer );
            this.fastIntegrationPlateSolveCheckBox.text = "";
            this.fastIntegrationPlateSolveCheckBox.onCheck = ( checked ) =>
            {
               engine.platesolve = checked;
            };
            this.fastIntegrationPlateSolveCheckBox.toolTip = fastIntegrationPlateSolveToolTip;

            let fastIntegrationPlateSolveSizer = new HorizontalSizer;
            fastIntegrationPlateSolveSizer.spacing = 4;
            fastIntegrationPlateSolveSizer.add( this.fastIntegrationPlateSolveLabel );
            fastIntegrationPlateSolveSizer.add( this.fastIntegrationPlateSolveCheckBox );
            fastIntegrationPlateSolveSizer.addStretch();

            rightContainerSizer.addSpacing( 8 );
            rightContainerSizer.add( fastIntegrationPlateSolveSizer );
         }

         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.linearPatternSubtractionControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.subframesWeightsEditControl );
         rightContainerSizer.add( this.subframesWeightingControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.frameSelectionControl );
         rightContainerSizer.add( this.frameSelectionSettingsControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.lightsRegistrationControl );
         rightContainerSizer.add( this.imageRegistrationControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.lightsNormalizationControl );
         rightContainerSizer.add( this.localNormalizationControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.lightsIntegrationControl );
         rightContainerSizer.add( this.imageIntegrationControl );
         if ( !engine.fastMode )
            rightContainerSizer.addSpacing( 8 );
         rightContainerSizer.add( this.platesolveControl );
         rightContainerSizer.add( this.imageSolverParametersControl );

         if ( engine.fastMode )
         {
            rightContainerSizer.addStretch();

            this.linearPatternSubtractionControl.visible = false;
            this.linearPatternSubtractionControl.__alwaysHidden__ = true;

            this.subframesWeightsEditControl.visible = false;
            this.subframesWeightsEditControl.__alwaysHidden__ = true;

            this.subframesWeightingControl.visible = false;
            this.subframesWeightingControl.__alwaysHidden__ = true;

            this.frameSelectionControl.visible = false;
            this.frameSelectionControl.__alwaysHidden__ = true;

            this.frameSelectionSettingsControl.visible = false;
            this.frameSelectionSettingsControl.__alwaysHidden__ = true;

            this.lightsRegistrationControl.visible = false;
            this.lightsRegistrationControl.__alwaysHidden__ = true;

            this.imageRegistrationControl.visible = false;
            this.imageRegistrationControl.__alwaysHidden__ = true;

            this.platesolveControl.visible = false;
            this.platesolveControl.__alwaysHidden__ = true;

            this.imageSolverParametersControl.visible = false;
            this.imageSolverParametersControl.__alwaysHidden__ = true;

            this.lightsNormalizationControl.visible = false;
            this.lightsNormalizationControl.__alwaysHidden__ = true;

            this.localNormalizationControl.visible = false;
            this.localNormalizationControl.__alwaysHidden__ = true;

            this.lightsIntegrationControl.visible = false;
            this.lightsIntegrationControl.__alwaysHidden__ = true;

            this.imageIntegrationControl.visible = false;
            this.imageIntegrationControl.__alwaysHidden__ = true;
         }

         break;
   }

   //

   this.sizer = new HorizontalSizer;
   this.sizer.margin = 8;
   this.sizer.add( this.treeBox, 100 );
   this.sizer.addSpacing( 12 );
   this.sizer.add( this.rightContainer );
   }
}

// ----------------------------------------------------------------------------

var ResetDialog = class extends WBPPDialog
{
   constructor()
   {
      super();

   //
   this.resetParametersCheckBox = new CheckBox( this );
   this.resetParametersCheckBox.text = "Reset all parameters";
   this.resetParametersCheckBox.checked = false;
   this.resetParametersCheckBox.onCheck = ( checked ) =>
   {
      this.resetParametersRadioButton.enabled = checked;
      this.reloadSettingsRadioButton.enabled = checked;
   }

   //

   this.resetParametersRadioButton = new RadioButton( this );
   this.resetParametersRadioButton.text = "to factory-default values";
   this.resetParametersRadioButton.checked = true;

   this.reloadSettingsRadioButton = new RadioButton( this );
   this.reloadSettingsRadioButton.text = "from the settings of the last session";

   let radioButtonsSizer = new VerticalSizer;
   radioButtonsSizer.spacing = 8;
   radioButtonsSizer.add( this.resetParametersRadioButton );
   radioButtonsSizer.add( this.reloadSettingsRadioButton );
   let radioOptionsSizer = new HorizontalSizer;
   radioOptionsSizer.addSpacing( 16 );
   radioOptionsSizer.add( radioButtonsSizer );

   this.clearFileListsCheckBox = new CheckBox( this );
   this.clearFileListsCheckBox.text = "Clear all file lists";
   this.clearFileListsCheckBox.checked = false;

   this.clearCacheCheckBox = new CheckBox( this );
   this.clearCacheCheckBox.text = "Purge cache";
   this.clearCacheCheckBox.checked = true;
   this.clearCacheCheckBox.visible = !engine.fastMode;

   //

   this.okButton = new PushButton( this );
   this.okButton.defaultButton = true;
   this.okButton.text = "OK";
   this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
   this.okButton.onClick = function()
   {
      this.dialog.ok();
   };

   this.cancelButton = new PushButton( this );
   this.cancelButton.text = "Cancel";
   this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
   this.cancelButton.onClick = function()
   {
      this.dialog.cancel();
   };

   this.buttonsSizer = new HorizontalSizer;
   this.buttonsSizer.addStretch();
   this.buttonsSizer.add( this.okButton );
   this.buttonsSizer.addSpacing( 8 );
   this.buttonsSizer.add( this.cancelButton );

   //

   this.sizer = new VerticalSizer;
   this.sizer.margin = 8;
   this.sizer.spacing = 6;
   this.sizer.add( this.resetParametersCheckBox );
   this.sizer.add( radioOptionsSizer );
   this.sizer.add( this.clearFileListsCheckBox );
   this.sizer.add( this.clearCacheCheckBox );
   this.sizer.add( this.buttonsSizer );

   this.ensureLayoutUpdated();
   this.adjustToContents();
   this.setFixedSize();

   this.windowTitle = "Reset Engine";
   }
}

// ----------------------------------------------------------------------------

var SelectCustomFilesDialog = class extends WBPPDialog
{
   constructor()
   {
      super();

   this.imageType = ImageType.Unknown;
   this.filter = "?"; // ### see StackEngine.addFile()
   this.binning = 0;
   this.exposureTime = 0;
   this.files = new Array;

   let labelWidth1 = this.font.width( "Exposure time (s):" + "M" );

   //

   this.fileListLabel = new Label( this );
   this.fileListLabel.text = "Selected Files";

   this.fileList = new StyledTreeBox( this );
   this.fileList.numberOfColumns = 1;
   this.fileList.headerVisible = false;
   this.fileList.setScaledMinSize( 400, 250 );

   this.addButton = new PushButton( this );
   this.addButton.text = "Files";
   this.addButton.icon = this.scaledResource( ":/icons/add.png" );
   this.addButton.toolTip = "<p>Add files to the input files list.</p>";
   this.addButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Images";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         for ( let i = 0; i < ofd.filePaths.length; ++i )
            this.dialog.files.push( ofd.filePaths[ i ] );
         this.dialog.updateFileList();
      }
   };

   this.clearButton = new PushButton( this );
   this.clearButton.text = "Clear";
   this.clearButton.icon = this.scaledResource( ":/icons/clear.png" );
   this.clearButton.toolTip = "<p>Clear the current list of input files.</p>";
   this.clearButton.onClick = function()
   {
      this.dialog.files = new Array;
      this.dialog.updateFileList();
   };

   this.fileButtonsSizer = new HorizontalSizer;
   this.fileButtonsSizer.addUnscaledSpacing( labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.fileButtonsSizer.add( this.addButton );
   this.fileButtonsSizer.addSpacing( 8 );
   this.fileButtonsSizer.add( this.clearButton );
   this.fileButtonsSizer.addStretch();

   //

   let imageTypeToolTip = "<p>Frame type. Select '?' to determine frame types automatically.</p>";

   this.imageTypeLabel = new Label( this );
   this.imageTypeLabel.text = "Image type:";
   this.imageTypeLabel.minWidth = labelWidth1;
   this.imageTypeLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.imageTypeLabel.toolTip = imageTypeToolTip;

   this.imageTypeComboBox = new ComboBox( this );
   this.imageTypeComboBox.addItem( "?" );
   this.imageTypeComboBox.addItem( "Bias frame" );
   this.imageTypeComboBox.addItem( "Dark frame" );
   this.imageTypeComboBox.addItem( "Flat field" );
   this.imageTypeComboBox.addItem( "Light frame" );
   this.imageTypeComboBox.currentItem = this.imageType; // ImageType property -> combobox item (PJSR values match combobox indices)
   this.imageTypeComboBox.toolTip = imageTypeToolTip;
   this.imageTypeComboBox.onItemSelected = function( item )
   {
      this.dialog.imageType = item; // combobox item -> ImageType property (PJSR values match combobox indices)
   };

   this.imageTypeSizer = new HorizontalSizer;
   this.imageTypeSizer.spacing = 4;
   this.imageTypeSizer.add( this.imageTypeLabel );
   this.imageTypeSizer.add( this.imageTypeComboBox, 100 );

   //

   let filterToolTip = "<p>Filter name. Specify a single question mark '?' to determine filters automatically.</p>";

   this.filterLabel = new Label( this );
   this.filterLabel.text = "Filter name:";
   this.filterLabel.minWidth = labelWidth1;
   this.filterLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.filterLabel.toolTip = filterToolTip;

   this.filterEdit = new Edit( this );
   this.filterEdit.text = this.filter;
   this.filterEdit.toolTip = filterToolTip;
   this.filterEdit.onEditCompleted = function()
   {
      this.text = this.dialog.filter = this.text.trim();
   };

   this.filterSizer = new HorizontalSizer;
   this.filterSizer.spacing = 4;
   this.filterSizer.add( this.filterLabel );
   this.filterSizer.add( this.filterEdit, 100 );

   //

   let binningToolTip = "<p>Pixel binning. Specify zero to determine binnings automatically.</p>";

   this.binningLabel = new Label( this );
   this.binningLabel.text = "Binning:";
   this.binningLabel.minWidth = labelWidth1;
   this.binningLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   this.binningLabel.toolTip = binningToolTip;

   this.binningSpinBox = new SpinBox( this );
   this.binningSpinBox.minValue = 0;
   this.binningSpinBox.maxValue = 4;
   this.binningSpinBox.value = this.binning;
   this.binningSpinBox.toolTip = binningToolTip;
   this.binningSpinBox.onValueUpdated = function( value )
   {
      this.dialog.binning = value;
   };

   this.binningSizer = new HorizontalSizer;
   this.binningSizer.spacing = 4;
   this.binningSizer.add( this.binningLabel );
   this.binningSizer.add( this.binningSpinBox );
   this.binningSizer.addStretch();

   //

   this.exposureTimeEdit = new NumericEdit( this );
   this.exposureTimeEdit.label.text = "Exposure time (s):";
   this.exposureTimeEdit.label.minWidth = labelWidth1;
   this.exposureTimeEdit.setRange( 0, 999999 );
   this.exposureTimeEdit.setPrecision( 2 );
   this.exposureTimeEdit.setValue( this.exposureTime );
   this.exposureTimeEdit.toolTip = "<p>Exposure time in seconds. Specify zero to determine exposure times automatically.</p>";
   this.exposureTimeEdit.sizer.addStretch();
   this.exposureTimeEdit.onValueUpdated = function( value )
   {
      this.dialog.exposureTime = value;
   };

   //

   this.okButton = new PushButton( this );
   this.okButton.defaultButton = true;
   this.okButton.text = "OK";
   this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
   this.okButton.onClick = function()
   {
      this.dialog.ok();
   };

   this.cancelButton = new PushButton( this );
   this.cancelButton.text = "Cancel";
   this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
   this.cancelButton.onClick = function()
   {
      this.dialog.cancel();
   };

   this.buttonsSizer = new HorizontalSizer;
   this.buttonsSizer.addUnscaledSpacing( labelWidth1 + this.logicalPixelsToPhysical( 4 ) );
   this.buttonsSizer.add( this.okButton );
   this.buttonsSizer.addSpacing( 8 );
   this.buttonsSizer.add( this.cancelButton );

   //

   this.sizer = new VerticalSizer;
   this.sizer.margin = 8;
   this.sizer.spacing = 6;
   this.sizer.add( this.fileListLabel );
   this.sizer.add( this.fileList, 100 );
   this.sizer.add( this.fileButtonsSizer );
   this.sizer.add( this.imageTypeSizer );
   this.sizer.add( this.filterSizer );
   this.sizer.add( this.binningSizer );
   this.sizer.add( this.exposureTimeEdit );
   this.sizer.add( this.buttonsSizer );

   this.ensureLayoutUpdated();
   this.adjustToContents();
   this.setMinSize();

   this.windowTitle = "Custom Frames";

   this.updateFileList = function()
   {
      this.fileList.clear();
      for ( let i = 0; i < this.files.length; ++i )
      {
         let node = new TreeBoxNode;
         node.setText( 0, File.extractNameAndExtension( this.files[ i ] ) );
         node.setToolTip( 0, this.files[ i ] );
         this.fileList.add( node );
      }
   };
   }
}

// ----------------------------------------------------------------------------

var StackDialog = class extends WBPPDialog
{
   constructor()
   {
      super();

   this.labelWidth1 = this.font.width( "Minimum structure size:" + "M" );
   this.textEditWidth = 25 * this.font.width( "M" );
   this.numericEditWidth = 6 * this.font.width( "0" );
   this.suffixEditWidth = 10 * this.font.width( "M" );
   this.rightPanelWidth = this.logicalPixelsToPhysical( 215 );

   // Tree node icons.
   this.masterFrameIcon = ":/bullets/bullet-star6-blue.svg";
   this.calibrationFrameIcon = ":/bullets/bullet-circle.svg";
   this.lightFrameIcon = ":/bullets/bullet-circle-blue.svg";

   // -------------------------------------------------------------------------
   // TAB BOX CONSTRUCTION
   // -------------------------------------------------------------------------

   this.calibrationPanelPreProcess = new CalibrationPanel( this, BPP.GroupingMode.PRE );
   this.calibrationPanelPostProcess = new PostCalibrationPanel( this );

   //

   this.pipelinePanel = new PipelinePanel( this );

   //

   this.tabBox = new TabBox( this );

   this.tabBox.addPage( new FileControl( this, ImageType.Bias ), "Bias" );
   this.tabBox.addPage( new FileControl( this, ImageType.Dark ), "Darks" );
   this.tabBox.addPage( new FileControl( this, ImageType.Flat ), "Flats" );
   this.tabBox.addPage( new FileControl( this, ImageType.Light ), "Lights" );
   this.tabBox.addPage( this.calibrationPanelPreProcess, "Calibration" );
   this.tabBox.addPage( this.calibrationPanelPostProcess, "Post-Calibration" );
   this.tabBox.addPage( this.pipelinePanel, "Pipeline" );

   // Handle click on file name -> set registration reference image
   this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) ).treeBox.onNodeDoubleClicked = function( node )
   {
      // We create a nodeData_filePath property for each TreeBox node to store
      // the full path of the corresponding frame group element.
      // -- See refreshTreeBoxes()
      if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL )
         if ( node.nodeData_filePath )
            if ( !WBPPUtils.isEmptyString( node.nodeData_filePath ) )
            {
               engine.referenceImage = node.nodeData_filePath;
               this.dialog.referenceImageControl.addingReferenceImage( node.nodeData_filePath );
            }
   };

   // ensure we regenearte the pipeline every time we open the pipeline panel
   this.tabBox.onPageSelected = ( pageIndex ) =>
   {
      if ( pageIndex == 6 )
         this.pipelinePanel.updateContent();
   };

   // -------------------------------------------------------------------------
   // BOTTOM BUTTONS CONSTRUCTION
   // -------------------------------------------------------------------------

   this.newInstanceButton = new ToolButton( this );
   this.newInstanceButton.icon = this.scaledResource( ":/process-interface/new-instance.png" );
   this.newInstanceButton.setScaledFixedSize( 24, 24 );
   this.newInstanceButton.toolTip = "New Instance";
   this.newInstanceButton.onMousePress = function()
   {
      this.hasFocus = true;
      engine.parametersManager.exportParameters();
      this.pushed = false;
      this.dialog.newInstance();
   };

   function insertFastImagingModeDiagnosticMessages()
   {
      if ( engine.automaticFIgroups.length > 0 )
      {
         engine.diagnosticMessages.unshift( "" );
         for ( let i = 0; i < engine.automaticFIgroups.length; i++ )
         {
            let group = engine.automaticFIgroups[ i ];
            engine.diagnosticMessages.unshift( "<b>Fast Integration</b> was automatically enabled for group " + group.toShortString() );
         }
      }
   }
   //

   this.addFolderButton = new PushButton( this );
   this.addFolderButton.text = "Directory";
   this.addFolderButton.icon = this.scaledResource( ":/icons/add.png" );
   this.addFolderButton.toolTip = "<p>Add image files to the input files list by scanning all files and folders recursively under the selected root folder.</p>";
   this.addFolderButton.onClick = () =>
   {
      let gdd = new GetDirectoryDialog;
      gdd.caption = "Select Root Directory";
      if ( gdd.execute() )
      {
         this.dialog.enabled = false;
         engine.resetAutomaticFastImagingModeGroups();
         console.show();
         let rootDir = gdd.directoryPath;

         // get the list of compatible file extensions
         let openFileSupport = new OpenFileDialog;
         openFileSupport.loadImageFilters();
         let filters = openFileSupport.filters[ 0 ]; // all known format
         filters.shift();
         filters = filters.concat( filters.map( f => ( f.toUpperCase() ) ) );

         let et = new ElapsedTime();

         // perform the search
         let filesFound = 0;
         let addedFiles = 0;
         let L = new FileList( rootDir, filters, false /*verbose*/ );
         L.files.forEach( ( filePath, i ) =>
         {
            engine.diagnosticMessages.push( "<b>found: </b>" + File.extractNameAndExtension( filePath ) );
            console.noteln( "adding [", i + 1, "/", L.files.length, "] ", filePath );
            console.flush();
            filesFound++;
            let result = engine.addFile( filePath );
            if ( result.success )
               addedFiles++;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         } );
         engine.diagnosticMessages.unshift( format( "=== %d frames found, %d added (in " + et.text + ") ===", filesFound, addedFiles ) );
         insertFastImagingModeDiagnosticMessages();

         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();

         this.dialog.enabled = true;
         console.hide();

         engine.diagnosticsManager.showDiagnosticMessages();
         engine.diagnosticsManager.clearDiagnosticMessages();
      }
   };

   this.fileAddButton = new PushButton( this );
   this.fileAddButton.text = "Files";
   this.fileAddButton.icon = this.scaledResource( ":/icons/add.png" );
   this.fileAddButton.toolTip = "<p>Add files to the input files list.</p>"
      + "<p>Image types will be selected automatically based on XISF image properties and/or FITS keywords.</p>";
   this.fileAddButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Images";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         this.dialog.enabled = false;
         engine.resetAutomaticFastImagingModeGroups();
         console.show();
         let n = 0;
         for ( let i = 0; i < ofd.filePaths.length; ++i )
         {
            let result = engine.addFile( ofd.filePaths[ i ] );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.diagnosticMessages.unshift( format( "=== %d of %d frames were added ===", n, ofd.filePaths.length ) );
         insertFastImagingModeDiagnosticMessages();

         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();

         this.dialog.enabled = true;
         console.hide();
         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {

            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   this.biasAddButton = new PushButton( this );
   this.biasAddButton.text = "Bias";
   this.biasAddButton.icon = this.scaledResource( ":/icons/add.png" );
   this.biasAddButton.toolTip = "<p>Add files to the input bias frames list.</p>"
      + "<p>Files will be added as bias frames unconditionally - no XISF property or FITS header keyword checks will be performed.</p>";
   this.biasAddButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Bias Frames";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         let n = 0;
         for ( let i = 0; i < ofd.filePaths.length; ++i )
         {
            let result = engine.addBiasFrame( ofd.filePaths[ i ] );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();
         this.dialog.tabBox.currentPageIndex = BPP.imageTypeIndex( ImageType.Bias );

         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {
            engine.diagnosticMessages.unshift( format( "=== %d of %d bias frames were added ===", n, ofd.filePaths.length ) );
            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   this.darkAddButton = new PushButton( this );
   this.darkAddButton.text = "Darks";
   this.darkAddButton.icon = this.scaledResource( ":/icons/add.png" );
   this.darkAddButton.toolTip = "<p>Add files to the input dark frames list.</p>"
      + "<p>Files will be added as dark frames unconditionally - no XISF property or FITS header keyword checks will be performed.</p>";
   this.darkAddButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Dark Frames";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         let n = 0;
         for ( let i = 0; i < ofd.filePaths.length; ++i )
         {
            let result = engine.addDarkFrame( ofd.filePaths[ i ] );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();
         this.dialog.tabBox.currentPageIndex = BPP.imageTypeIndex( ImageType.Dark );

         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {
            engine.diagnosticMessages.unshift( format( "=== %d of %d dark frames were added ===", n, ofd.filePaths.length ) );
            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   this.flatAddButton = new PushButton( this );
   this.flatAddButton.text = "Flats";
   this.flatAddButton.icon = this.scaledResource( ":/icons/add.png" );
   this.flatAddButton.toolTip = "<p>Add files to the input flat frames list.</p>"
      + "<p>Files will be added as flat frames unconditionally - no XISF property or FITS header checks will be performed.</p>";
   this.flatAddButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Flat Frames";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         let n = 0;
         for ( let i = 0; i < ofd.filePaths.length; ++i )
         {
            let result = engine.addFlatFrame( ofd.filePaths[ i ] );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();
         this.dialog.tabBox.currentPageIndex = BPP.imageTypeIndex( ImageType.Flat );

         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {
            engine.diagnosticMessages.unshift( format( "=== %d of %d flat frames were added ===", n, ofd.filePaths.length ) );
            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   this.lightAddButton = new PushButton( this );
   this.lightAddButton.text = "Lights";
   this.lightAddButton.icon = this.scaledResource( ":/icons/add.png" );
   this.lightAddButton.toolTip = "<p>Add files to the input light frames list.</p>"
      + "<p>Files will be added as light frames unconditionally - no XISF property or FITS header checks will be performed.</p>";
   this.lightAddButton.onClick = function()
   {
      let ofd = new OpenFileDialog;
      ofd.multipleSelections = true;
      ofd.caption = "Select Light Frames";
      ofd.loadImageFilters();
      if ( ofd.execute() )
      {
         engine.resetAutomaticFastImagingModeGroups();
         let n = 0;
         for ( let i = 0; i < ofd.filePaths.length; ++i )
         {
            let result = engine.addLightFrame( ofd.filePaths[ i ] );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.diagnosticMessages.unshift( format( "=== %d of %d light frames were added ===", n, ofd.filePaths.length ) );
         insertFastImagingModeDiagnosticMessages();

         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();
         this.dialog.tabBox.currentPageIndex = BPP.imageTypeIndex( ImageType.Light );

         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {
            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   this.customAddButton = new PushButton( this );
   this.customAddButton.text = "Add Custom";
   this.customAddButton.icon = this.scaledResource( ":/icons/document-edit.png" );
   this.customAddButton.toolTip = "<p>Add custom files to the input custom frames list.</p>";
   this.customAddButton.onClick = function()
   {
      let d = new SelectCustomFilesDialog;
      if ( d.execute() )
      {
         if ( d.imageType == ImageType.Light )
            engine.resetAutomaticFastImagingModeGroups();
         let n = 0;
         for ( let i = 0; i < d.files.length; ++i )
         {
            let result = engine.addFile( d.files[ i ], d.imageType, d.filter, d.binning, d.exposureTime );
            if ( result.success )
               ++n;
            else
               engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + result.message + DiagnosticsManager.warningPostfix );
         }
         engine.diagnosticMessages.unshift( format( "=== %d of %d custom frames were added ===", n, d.files.length ) );
         insertFastImagingModeDiagnosticMessages();

         engine.rebuild();
         this.dialog.refreshTreeBoxes();
         this.dialog.updateControls();
         this.dialog.tabBox.currentPageIndex = BPP.imageTypeIndex( d.imageType );

         if ( engine.diagnosticsManager.hasDiagnosticMessages() )
         {

            engine.diagnosticsManager.showDiagnosticMessages();
            engine.diagnosticsManager.clearDiagnosticMessages();
         }
      }
   };

   // -------------------------------------------------------------------------
   // OPTION FOR FBPP ONLY: load the current session in WBPP
   if ( engine.fastMode )
   {
      this.loadInWBPP = new PushButton( this );
      this.loadInWBPP.text = "WBPP";
      this.loadInWBPP.icon = this.scaledResource( ":/arrows/arrow-right.png" );
      this.loadInWBPP.toolTip = "<p>Loads the current session in the WBPP script.</p>";
      this.loadInWBPP.onClick = function()
      {
         engine.loadInWBPP = true
         this.dialog.ok();
      };
   }
   // -------------------------------------------------------------------------

   //

   // add actions combo box to be visible only on small screen as an alternative to the separate buttons

   this.addActionsLabel = new Label( this );
   this.addActionsLabel.text = "Add actions: ";
   this.addActionsLabel.textAlignment = TextAlignment.VertCenter;

   let addIcon = this.scaledResource( ":/icons/add.png" );
   let arrowIcon = this.scaledResource( ":/arrows/arrow-right.png" );
   let documentEditIcon = this.scaledResource( ":/icons/document-edit.png" );

   this.addActionsComboBox = new ComboBox( this );
   this.addActionsComboBox.__entries__ = [
   {
      label: "",
      control: undefined
   },
   {
      label: "Bias",
      icon: addIcon,
      control: this.biasAddButton
   },
   {
      label: "Darks",
      icon: addIcon,
      control: this.darkAddButton
   },
   {
      label: "Flats",
      icon: addIcon,
      control: this.flatAddButton
   },
   {
      label: "Lights",
      icon: addIcon,
      control: this.lightAddButton
   },
   {
      label: "Custom",
      icon: documentEditIcon,
      control: this.customAddButton
   }, ];

   if ( engine.fastMode )
   {
      this.addActionsComboBox.__entries__.push(
      {
         label: "WBPP",
         icon: arrowIcon,
         control: this.loadInWBPP
      } );
   }

   for ( let i = 0; i < this.addActionsComboBox.__entries__.length; ++i )
      if ( this.addActionsComboBox.__entries__[ i ].icon )
         this.addActionsComboBox.addItem( this.addActionsComboBox.__entries__[ i ].label, this.addActionsComboBox.__entries__[ i ].icon );
      else
         this.addActionsComboBox.addItem( this.addActionsComboBox.__entries__[ i ].label );

   this.addActionsComboBox.onItemSelected = ( itemIndex ) =>
   {
      // reset the selection
      this.addActionsComboBox.currentItem = 0;

      // perform the selected action
      if ( this.addActionsComboBox.__entries__[ itemIndex ].control )
         this.addActionsComboBox.__entries__[ itemIndex ].control.onClick()
   };

   //

   this.resetButton = new PushButton( this );
   this.resetButton.text = "Reset";
   this.resetButton.icon = this.scaledResource( ":/icons/reload.png" );
   this.resetButton.toolTip = "<p>Perform optional reset and clearing actions.</p>";
   this.resetButton.onClick = function()
   {
      let d = new ResetDialog;
      if ( d.execute() )
      {
         // reset parameters
         if ( d.resetParametersCheckBox.checked )
         {
            if ( d.resetParametersRadioButton.checked )
               engine.parametersManager.setDefaultParameters();
            if ( d.reloadSettingsRadioButton.checked )
               engine.parametersManager.loadSettings();

            // Clear frame filter configs and rejection states from all groups
            let groups = engine.groupsManager.groups;
            for ( let i = 0; i < groups.length; i++ )
            {
               groups[ i ].clearFrameFilterConfig();
               groups[ i ].clearFrameRejectionState();
            }
         }
         // clear file list
         if ( d.clearFileListsCheckBox.checked )
         {
            engine.groupsManager.clear();
            engine.groupsManager.clearCache();
         }
         // clear cache
         if ( d.clearCacheCheckBox.checked )
            engine.executionCache.reset();
         // refresh
         this.dialog.updateControls();
         this.dialog.keywordsEditor.reset();
      }
   };

   //

   this.diagnosticsButton = new PushButton( this );
   this.diagnosticsButton.defaultButton = true;
   this.diagnosticsButton.text = "Diagnostics";
   this.diagnosticsButton.icon = this.scaledResource( ":/icons/gear.png" );
   this.diagnosticsButton.toolTip = "<p>Check validity of selected files and processes.</p>";
   this.diagnosticsButton.onClick = () =>
   {
      engine.diagnosticsManager.runDiagnostics();
      let action = engine.diagnosticsManager.showDiagnosticMessages( false, true );
      engine.diagnosticsManager.clearDiagnosticMessages();

      if ( action == BPP.Format.StdDialogCode_GenerateScreenshots )
         this.generateScreenshots();
   };

   this.exportTestButton = new ToolButton( this );
   this.exportTestButton.icon = this.scaledResource( ":/icons/item-export.png" );
   this.exportTestButton.setScaledFixedSize( 20, 20 );
   this.exportTestButton.toolTip = "<p>Exports the current configuration into a test file to be used in automation mode.</p.>";
   this.exportTestButton.onClick = () =>
   {
      let sfd = new SaveFileDialog;
      sfd.caption = "BPP Test file export";
      sfd.overwritePrompt = true;
      if ( sfd.execute() )
      {
         engine.parametersManager.exportTest( File.changeExtension( sfd.filePath, engine.fastMode ? ".fbpptest" : ".wbpptest" ) );
         this.dialog.updateControls();
      }
   };
   this.exportTestButton.visible = engine.testLoadOnly || false;
   this.onKeyPress = ( key, modifiers ) =>
   { // Ctrl+Shift+Alt+T: Toggle export test button visibility
      if ( key == 84 && modifiers == 23 )
         this.exportTestButton.visible = !this.exportTestButton.visible;

      // Alt+A (Windows/Linux) or Option+A (macOS): Show automation help
      // key 65 = 'A', modifiers 2 = Alt/Option, modifiers 4 = Ctrl
      if ( key == 65 && ( modifiers == 2 || modifiers == 4 ) )
      {
         console.show();
         printAutomationHelp( engine.fastMode );
      }
   };

   //

   this.runButton = new PushButton( this );
   this.runButton.text = "Run";
   this.runButton.icon = this.scaledResource( ":/icons/power.png" );
   this.runButton.onClick = function()
   {
      this.dialog.calibrationPanelPreProcess.deselectNode();
      this.dialog.ok();
   };

   this.exitButton = new PushButton( this );
   this.exitButton.text = "Exit";
   this.exitButton.icon = this.scaledResource( ":/icons/close.png" );
   this.exitButton.onClick = function()
   {
      this.dialog.cancel();
   };

   this.buttonsSizer = new HorizontalSizer;
   this.buttonsSizer.spacing = 6;
   this.buttonsSizer.add( this.newInstanceButton );
   this.buttonsSizer.add( this.addActionsLabel );
   this.buttonsSizer.add( this.addActionsComboBox );
   this.buttonsSizer.add( this.addFolderButton );
   this.buttonsSizer.add( this.fileAddButton );
   this.buttonsSizer.add( this.biasAddButton );
   this.buttonsSizer.add( this.darkAddButton );
   this.buttonsSizer.add( this.flatAddButton );
   this.buttonsSizer.add( this.lightAddButton );
   this.buttonsSizer.add( this.customAddButton );
   if ( engine.fastMode )
      this.buttonsSizer.add( this.loadInWBPP );
   this.buttonsSizer.addSpacing( 24 );
   this.buttonsSizer.addStretch();
   this.buttonsSizer.add( this.resetButton );
   this.buttonsSizer.addStretch();
   this.buttonsSizer.addSpacing( 24 );
   this.buttonsSizer.add( this.exportTestButton );
   this.buttonsSizer.add( this.diagnosticsButton );
   this.buttonsSizer.add( this.runButton );
   this.buttonsSizer.add( this.exitButton );

   // -------------------------------------------------------------------------
   // RIGHT SIDE CONTENT - GLOBAL OPTIONS CONSTRUCTION
   // -------------------------------------------------------------------------

   this.GUIsizeControl = new Control( this );
   this.GUIsizeControl.setMaxWidth( this.rightPanelWidth );
   this.GUIsizeControl.sizer = new HorizontalSizer;
   this.GUIsizeControl.sizer.spacing = 8;

   this.switchModeToolButton = new ToolButton( this.GUIsizeControl );
   this.switchModeToolButton.icon = this.scaledResource( ":/web-browser/zoom-auto.png" );
   this.switchModeToolButton.setScaledFixedSize( 20, 20 );
   this.switchModeToolButton.toolTip = "<p>When the compact GUI mode is enabled, this button alternates the visibility between the global "
      + "options and the selected group options.</p.>";
   this.switchModeToolButton.onClick = () =>
   {
      engine.globalOptionsHidden = !engine.globalOptionsHidden;
      this.updateControls();
   };
   this.switchModeToolButton.adjustToContents();

   this.GUIsizeControl.sizer.addStretch();
   this.GUIsizeControl.sizer.add( this.switchModeToolButton );
   this.GUIsizeControlMinWidth = 40;

   //

   this.globalOptionsContainer = new Control( this );
   this.globalOptionsContainer.setMaxWidth( this.rightPanelWidth );

   //

   this.descriptionLabel = new Label( this.globalOptionsContainer );
   this.descriptionLabel.cssId = "SCPInfoLabel";
   this.descriptionLabel.setMaxWidth( this.rightPanelWidth );
   this.descriptionLabel.margin = 4;
   this.descriptionLabel.wordWrapping = true;
   this.descriptionLabel.useRichText = true;
   this.descriptionLabel.text =
      (engine.fastMode
      ? "<p><b>A script for fast image calibration, registration, and integration.</b></p>"
      : "<p><b>A script to preprocess, register, and integrate images.</b></p>")
      + format( "<p style=\"font-size: %dpt;\"><br/>", (CoreApplication.platform == "macOS") ? 9 : 6 )
      + "Copyright &copy; 2019-2026 Roberto Sartori<br/>"
      + "Copyright &copy; 2020-2021 Adam Block<br/>"
      + "Copyright &copy; 2019 Tommaso Rubechi<br/>"
      + "Copyright &copy; 2012 Kai Wiechen<br/>"
      + "Copyright &copy; 2012-2026 Pleiades Astrophoto</p>";

   //

   this.helpButton = new ToolButton( this.globalOptionsContainer );
   this.helpButton.icon = this.scaledResource( ":/icons/comment.png" );
   this.helpButton.setScaledFixedSize( 20, 20 );
   this.helpButton.toolTip =
        "<ol>"
      + "<li>Select the Bias tab and load either raw bias frames or a master bias.<br/></li>"
      + "<li>Select the Darks tab and repeat the process in step 1. Load flats that match filters of your Lights.<br/></li>"
      + "<li>Select the Flats tab and again repeat the process in step 1. Load flats for all the filters you will load in Lights.<br/></li>"
      + "<li>Select the Lights tab and load all the light frames you wish (you can load all filters in a single operation).<br/></li>"
      + "<li>Select a Light frame as the <i>registration reference</i>. You can select it by simply double-clicking on the list or you can "
      +     "flag the option for the automatic selection.<br/></li>"
      + "<li>Select an output directory.<br/></li>"
      + "<li>Select the Control Panel to set the correct settings/relationships between frames and look at the calibration diagram.<br/></li>"
      + "<li>Click Run and grab a cup of coffee or a glass of wine. Some bourbon also works.<br/></li>"
      + "<li>The script will output the calibrated and registered light frames along with the generated master frames on the output directory, "
      +     "in subfolders named <i>\"calibrated\"</i>, <i>\"registered\"</i> and <i>\"master\"</i>.<br/></li>"
      + "</ol>";

   let helpButtonSizer = new HorizontalSizer;
   helpButtonSizer.add( this.helpButton );
   helpButtonSizer.addStretch();

   //

   this.presetsControl = new PresetsControl( "Presets", this.globalOptionsContainer );
   this.presetsControl.setMaxWidth( this.rightPanelWidth );
   this.presetsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIPresetsCollapsed = collapsed;
   };

   this.presetsControl.visible = !engine.fastMode;

   //

   this.keywordsEditor = new KeywordsEditor( "Grouping Keywords", this.globalOptionsContainer );
   this.keywordsEditor.setActivatableCheckboxTooltip( "<p>Enable or disable the grouping by the listed keywords.</p>" )
   this.keywordsEditor.setMaxWidth( this.rightPanelWidth );
   engine.groupingKeywordsEnabled ? this.keywordsEditor.activate() : this.keywordsEditor.deactivate();
   this.keywordsEditor.onKeywordsUpdated = () =>
   {
      engine.rebuild();
      this.updateControls();
      this.dialog.update();
   };
   this.keywordsEditor.onCollapse = ( collapsed ) =>
   {
      engine.GUIKeywordsCollapsed = collapsed;
   };

   //

   this.globalOptionsControl = new GlobalOptionsControl( "Global Options", this.globalOptionsContainer );
   this.globalOptionsControl.setMaxWidth( this.rightPanelWidth );
   this.globalOptionsControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIGlobalOptionsCollapsed = collapsed;
   };

   //

   this.referenceImageControl = new RegistrationReferenceImageControl( "Registration Reference Image", this.globalOptionsContainer );
   this.referenceImageControl.setMaxWidth( this.rightPanelWidth );
   this.referenceImageControl.enabled = engine.imageRegistration;
   this.referenceImageControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIReferenceFrameCollapsed = collapsed;
   };

   //

   this.outputDirControl = new OutputDirectoryControl( "Output Directory", this.globalOptionsContainer );
   this.outputDirControl.setMaxWidth( this.rightPanelWidth );
   this.outputDirControl.onCollapse = ( collapsed ) =>
   {
      engine.GUIOutputDirCollapsed = collapsed;
   };

   //

   this.globalOptionsContainer.sizer = new VerticalSizer;
   this.settingsSizer = this.globalOptionsContainer.sizer;
   this.settingsSizer.spacing = 8;
   this.settingsSizer.add( this.descriptionLabel );
   this.settingsSizer.add( helpButtonSizer );
   this.settingsSizer.addStretch();
   this.settingsSizer.add( this.presetsControl );
   this.settingsSizer.add( this.keywordsEditor );
   this.settingsSizer.add( this.globalOptionsControl );
   this.settingsSizer.add( this.referenceImageControl );
   this.settingsSizer.add( this.outputDirControl );

   //

   let rightControlsSizer = new VerticalSizer;
   rightControlsSizer.spacing = 4;
   rightControlsSizer.add( this.GUIsizeControl );
   rightControlsSizer.addStretch();
   rightControlsSizer.add( this.globalOptionsContainer );

   //

   let mainSizer = new HorizontalSizer;
   mainSizer.spacing = 8;
   mainSizer.add( this.tabBox );
   mainSizer.add( rightControlsSizer );

   //

   this.sizer = new VerticalSizer;
   this.sizer.margin = 8;
   this.sizer.spacing = 8;
   this.sizer.add( mainSizer );
   this.sizer.add( this.buttonsSizer );

   //

   this.windowTitle = engine.title + ' ' + engine.version;

   /**
    * Auto-generation of the WBPP screenshots
    *
    * @return {*}
    */
   this.generateScreenshots = () =>
   {
      if ( !engine.outputDirectory )
         return;

      let outputDir = WBPPUtils.existingDirectory( engine.outputDirectory + "/logs" );

      let curPage = this.tabBox.currentPageIndex;
      let w = this.width;
      let h = this.height;

      this.width = 1920 * 1.5;
      this.height = 1080 * 1.5;

      for ( let i = 0; i < this.tabBox.numberOfPages; ++i )
      {
         this.tabBox.currentPageIndex = i;

         let bmp = this.render();
         let outputFile = outputDir + "/" + "0" + i + "_" + this.tabBox.pageLabel( i ) + ".jpg";
         bmp.save( outputFile, 80 );
      }

      this.width = w;
      this.height = h;
      this.tabBox.currentPageIndex = curPage;
   };

   this.onResize = () =>
   {
      this.updateWithResize();
   };

   this.adjustBottomButtonsVisibility = () =>
   {
      // handle add buttons (depending on the horizontal resizing)
      let resizedSmall = this.width < 1300 * this.displayPixelRatio;

      this.addActionsLabel.visible = resizedSmall;
      this.addActionsComboBox.visible = resizedSmall;

      // hide the following buttons on small GUI
      this.biasAddButton.visible = !resizedSmall;
      this.darkAddButton.visible = !resizedSmall;
      this.flatAddButton.visible = !resizedSmall;
      this.lightAddButton.visible = !resizedSmall;
      this.customAddButton.visible = !resizedSmall && !engine.fastMode;
   }

   this.updateWithResize = () =>
   {
      let updateControlRequired = false;
      if ( this.resizedOnce == undefined )
      {
         // first time the view is resized
         this.resizedOnce = true;
         updateControlRequired = true;
      }

      this.adjustBottomButtonsVisibility();

      if ( updateControlRequired )
      {
         this.updateControls();
         // dynamic window sizing
         this.onResizeRefreshTimer = new Timer( 0 /*interval*/ , false /*periodic*/ );
         this.onResizeRefreshTimer.onTimeout = () =>
         {
            this.resize( this.width - 1, this.height - 1 );
            this.center( this.width, this.height );
         };
         this.onResizeRefreshTimer.start();
      }

      // schedule the update of the controls
      this.adjustForSmallInterfaceTimer = new Timer( 0 /*interval*/ , false /*periodic*/ );
      this.adjustForSmallInterfaceTimer.onTimeout = () =>
      {
         this.adjustForSmallInterface();
      };
      this.adjustForSmallInterfaceTimer.start();
   };

   this.adjustForSmallInterface = () =>
   {
      let compactGUI = engine.enableCompactGUI;
      if ( this.lastCompactGUI != undefined && this.lastCompactGUI == compactGUI )
         return;

      this.lastCompactGUI = compactGUI;
      this.switchModeToolButton.visible = compactGUI;

      // hide the copyright to make more sapce on small screens
      this.descriptionLabel.visible = !compactGUI;
      this.switchModeToolButton.visible = compactGUI;

      // adjust controls for small GUI if needed
      // make bias controls collapsable
      let biasPage = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Bias ) );
      biasPage.biasOverscanControl.makeCollapsable( compactGUI )
      biasPage.biasOverscanControl.collapse( engine.GUIBiasPageOverscanControlCollapsed );
      biasPage.imageIntegrationControl.makeCollapsable( compactGUI )
      biasPage.imageIntegrationControl.collapse( engine.GUIBiasPageImageIntegrationControlCollapsed );

      let darkPage = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Dark ) );
      darkPage.imageIntegrationControl.makeCollapsable( compactGUI )
      darkPage.imageIntegrationControl.collapse( engine.GUIDarkPageImageIntegrationControlCollapsed );

      let flatPage = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Flat ) );
      flatPage.imageIntegrationControl.makeCollapsable( compactGUI )
      flatPage.imageIntegrationControl.collapse( engine.GUIFlatPageImageIntegrationControlCollapsed );

      let lightPage = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) );
      lightPage.linearPatternSubtractionControl.makeCollapsable( compactGUI )
      lightPage.linearPatternSubtractionControl.collapse( engine.GUILightPageLPSControlCollapsed );
      lightPage.subframesWeightingControl.makeCollapsable( compactGUI )
      lightPage.subframesWeightingControl.collapse( engine.GUILightPageSubframeWeightingControlCollapsed );
      lightPage.frameSelectionControl.makeCollapsable( compactGUI )
      lightPage.frameSelectionControl.collapse( engine.GUILightPageFrameSelectionControlCollapsed );
      lightPage.lightsRegistrationControl.makeCollapsable( compactGUI )
      lightPage.lightsRegistrationControl.collapse( engine.GUILightPageRegistrationControlCollapsed );
      lightPage.platesolveControl.makeCollapsable( compactGUI )
      lightPage.platesolveControl.collapse( engine.GUIPlatesolveControlCollapsed );
      lightPage.lightsNormalizationControl.makeCollapsable( compactGUI )
      lightPage.lightsNormalizationControl.collapse( engine.GUILightPageNormalizationControlCollapsed );
      lightPage.lightsIntegrationControl.makeCollapsable( compactGUI )
      lightPage.lightsIntegrationControl.collapse( engine.GUILightPageIntegrationControlCollapsed );

      // make per-group controls collapsable and collapse
      this.calibrationPanelPreProcess.overscanSettingsControl.makeCollapsable( compactGUI );
      this.calibrationPanelPreProcess.overscanSettingsControl.collapse( engine.GUIGroupOverscanSettingsCollapsed );

      this.calibrationPanelPreProcess.calibrationSettingsControl.makeCollapsable( compactGUI );
      this.calibrationPanelPreProcess.calibrationSettingsControl.collapse( engine.GUIGroupCalibrationSettingsCollapsed );

      this.calibrationPanelPreProcess.pedestalSettingsControl.makeCollapsable( compactGUI );
      this.calibrationPanelPreProcess.pedestalSettingsControl.collapse( engine.GUIGroupPedestalSettingsCollapsed );

      this.calibrationPanelPreProcess.cosmeticCorrectionSettingsControl.makeCollapsable( compactGUI );
      this.calibrationPanelPreProcess.cosmeticCorrectionSettingsControl.collapse( engine.GUIGroupCCSettingsCollapsed );

      this.calibrationPanelPreProcess.debayerSettingsControl.makeCollapsable( compactGUI );
      this.calibrationPanelPreProcess.debayerSettingsControl.collapse( engine.GUIGroupDebayerSettingsCollapsed );

      // make global controls collapsable and collapse
      this.presetsControl.makeCollapsable( compactGUI );
      this.presetsControl.collapse( engine.GUIPresetsCollapsed );
      this.keywordsEditor.makeCollapsable( compactGUI );
      this.keywordsEditor.collapse( engine.GUIKeywordsCollapsed );

      this.globalOptionsControl.makeCollapsable( compactGUI );
      this.globalOptionsControl.collapse( engine.GUIGlobalOptionsCollapsed );

      this.referenceImageControl.makeCollapsable( compactGUI );
      this.referenceImageControl.collapse( engine.GUIReferenceFrameCollapsed );

      this.outputDirControl.makeCollapsable( compactGUI );
      this.outputDirControl.collapse( engine.GUIOutputDirCollapsed );
   };

   /*
    * Automatic dialog layout, normal or compact mode.
    */
   this.selfAdjustFrame = () =>
   {
      this.setVariableSize();
      this.adjustForSmallInterface();
      this.updateControls();
      this.ensureLayoutUpdated();
      this.adjustToContents();
      this.setMinSize( engine.enableCompactGUI ? 900 * this.displayPixelRatio
         : Math.max( this.width, 1300 * this.displayPixelRatio ), this.height );
      this.adjustToContents();
      this.center( this.width, this.height );
      this.adjustBottomButtonsVisibility();
   };

   this.onShow = () =>
   {
      /*
       * Prefer to set layout dimensions and the current TabBox page once the
       * dialog is visible. This ensures that all controls will have calculated
       * their geometries and relative positions.
       */
      this.tabBox.currentPageIndex = 4 /*Calibration*/ ;
      this.selfAdjustFrame();
   };
   }

   clearTab( imageType )
   {
      let index = BPP.imageTypeIndex( imageType );
      if ( this.dialog.tabBox.pageControlByIndex( index ).treeBox )
         this.dialog.tabBox.pageControlByIndex( index ).treeBox.clear();
      engine.groupsManager.deleteFrameSet( imageType );
   }

   updateControls()
   {
      engine.rebuild();
      this.refreshTreeBoxes();

      for ( let i = 0; i < 4; ++i )
      {
         let page = this.tabBox.pageControlByIndex( i );

         if ( engine.enableCompactGUI )
            page.rightContainer.visible = engine.globalOptionsHidden;

         switch ( i )
         {
            case BPP.imageTypeIndex( ImageType.Bias ):
               page.biasOverscanControl.updateControls();
               page.overscanControl.updateControls();
               break;

            case BPP.imageTypeIndex( ImageType.Dark ):
               page.darkOptimizationThresholdControl.setValue( engine.darkOptimizationLow );
               page.darkExposureToleranceSpinBox.value = engine.darkExposureTolerance;
               break;

            case BPP.imageTypeIndex( ImageType.Flat ):
               break;

            case BPP.imageTypeIndex( ImageType.Light ):
               page.showAstrometricInfoButton.text = ( engine.showAstrometricInfo ? "Hide" : "Show" ) + " Astrometry";
               page.lightExposureToleranceSpinBox.value = engine.lightExposureTolerance;
               if ( page.fastIntegrationPlateSolveCheckBox )
                  page.fastIntegrationPlateSolveCheckBox.checked = engine.platesolve;
               page.linearPatternSubtractionControl.updateControls();
               page.lightsRegistrationControl.updateControls();
               page.platesolveControl.updateControls();
               page.lightsNormalizationControl.updateControls();
               page.imageRegistrationControl.updateControls();
               page.imageSolverParametersControl.updateControls();
               page.localNormalizationControl.updateControls();
               page.subframesWeightingControl.updateControls();
               page.subframesWeightsEditControl.updateControls();
               page.frameSelectionControl.updateControls();
               page.frameSelectionSettingsControl.updateControls();
               page.lightsIntegrationControl.updateControls();
               break;
         }

         page.imageIntegrationControl.updateControls();
      }

      if ( engine.enableCompactGUI )
      {
         this.tabBox.pageControlByIndex( 4 ).rightContainer.visible = engine.globalOptionsHidden;
         this.tabBox.pageControlByIndex( 5 ).rightContainer.visible = engine.globalOptionsHidden;
         this.tabBox.pageControlByIndex( 6 ).rightContainer.visible = engine.globalOptionsHidden;
         this.globalOptionsContainer.visible = !engine.globalOptionsHidden;
         if ( engine.globalOptionsHidden )
            this.GUIsizeControl.setMaxWidth( this.GUIsizeControlMinWidth );
         else
            this.GUIsizeControl.setMaxWidth( this.rightPanelWidth );
      }
      else
      {
         for ( let i = 0; i < this.tabBox.numberOfPages; ++i )
            this.tabBox.pageControlByIndex( i ).rightContainer.visible = true;

         this.globalOptionsContainer.visible = true;
         this.GUIsizeControl.setMaxWidth( this.rightPanelWidth );
      }

      this.calibrationPanelPreProcess.updateContent();
      this.calibrationPanelPostProcess.updateContent();

      // TODO
      // REFRESH TAB 5 for RGB recombination depending on integration status
      // -------------------------------------------------------------------

      // pipeline
      this.tabBox.pageControlByIndex( 6 ).updateContent();

      // refresh the global control panels
      this.globalOptionsControl.updateControls();
      this.outputDirControl.updateControls();
      this.referenceImageControl.updateControls();
      this.keywordsEditor.updateContent();
   }

   refreshTreeBoxes()
   {
      // reset all but the last tab
      for ( let j = 0; j < 4; ++j )
         this.tabBox.pageControlByIndex( j ).treeBox.clear();

      // determine the number of columns for the light treebox
      let lightTreeBox = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) ).treeBox;
      lightTreeBox.numberOfColumns = engine.showAstrometricInfo ? 7 : 1;
      lightTreeBox.headerVisible = lightTreeBox.numberOfColumns > 1;
      lightTreeBox.setHeaderText( 0, "Light frames" );
      if ( engine.showAstrometricInfo )
      {
         lightTreeBox.setHeaderText( 1, "Observation Time\nUTC" );
         lightTreeBox.setHeaderAlignment( 1, TextAlignment.Center );
         lightTreeBox.setHeaderText( 2, "Right Ascension\nh\u2003m\u2003s" );
         lightTreeBox.setHeaderAlignment( 2, TextAlignment.Center );
         lightTreeBox.setHeaderText( 3, "Declination\n\u00B0\u2003\u2032\u2003\u2033" );
         lightTreeBox.setHeaderAlignment( 3, TextAlignment.Center );
         lightTreeBox.setHeaderText( 4, "Focal Length\nmm" );
         lightTreeBox.setHeaderAlignment( 4, TextAlignment.Center );
         lightTreeBox.setHeaderText( 5, "Pixel Size\n\u03BCm" );
         lightTreeBox.setHeaderAlignment( 5, TextAlignment.Center );
         lightTreeBox.setHeaderText( 6, "" ); // last stretching column
      }

      // scan all groups BUT process only groups in pre-processing mode
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      let keywords = engine.keywords.keywordsForMode( BPP.GroupingMode.PRE );
      let tree = {};
      for ( let i = 0; i < groups.length; ++i )
      {
         let frameGroup = groups[ i ];

         let imageType = frameGroup.imageType;
         let binning = frameGroup.binning.toString();
         let filter = frameGroup.filter;

         let node;
         let treeNode;
         let nodeKey = "";

         nodeKey += imageType;
         if ( !tree.hasOwnProperty( nodeKey ) )
         {
            tree[ nodeKey ] = {};
            treeNode = tree[ nodeKey ];
         }
         else
         {
            treeNode = tree[ nodeKey ];
            node = treeNode.node;
         }

         nodeKey += "_" + binning + "_" + frameGroup.sizeString()
         if ( !treeNode.hasOwnProperty( nodeKey ) )
         {
            node = new TreeBoxNode;
            this.tabBox.pageControlByIndex( BPP.imageTypeIndex( imageType ) ).treeBox.add( node );
            node.expanded = true;
            node.setText( 0, "Binning " + binning + " (" + frameGroup.sizeString() + ")" );
            node.nodeData_type = "FrameGroup";
            node.nodeData_indexes = [ i ];
            treeNode[ nodeKey ] = {};
            treeNode[ nodeKey ].node = node;
            treeNode = treeNode[ nodeKey ];
         }
         else
         {
            treeNode = treeNode[ nodeKey ];
            node = treeNode.node;
            node.nodeData_indexes.push( i );
         }

         // BIASes and DARKs are not grouped by filter
         if ( imageType != ImageType.Bias )
         {
            if ( imageType != ImageType.Dark )
            {
               let filterName = ( filter.length > 0 ) ? filter : 'NoFilter';
               nodeKey += "_" + filterName;
               if ( !treeNode.hasOwnProperty( nodeKey ) )
               {
                  node = new TreeBoxNode( node );
                  node.expanded = true;
                  node.setText( 0, filterName );
                  node.nodeData_type = "FrameGroup";
                  node.nodeData_indexes = [ i ];
                  treeNode[ nodeKey ] = {};
                  treeNode[ nodeKey ].node = node;
                  treeNode[ nodeKey ].inexes = [ i ];
                  treeNode = treeNode[ nodeKey ];
               }
               else
               {
                  treeNode = treeNode[ nodeKey ];
                  node = treeNode.node;
                  node.nodeData_indexes.push( i );
               }
            }

            let exposureTimesString = frameGroup.exposureTimesToString();
            nodeKey += "_" + exposureTimesString;
            if ( !treeNode.hasOwnProperty( nodeKey ) )
            {

               node = new TreeBoxNode( node );
               node.expanded = true;
               node.useRichText = true;
               if ( keywords.length > 0 )
                  node.setText( 0, frameGroup.exposureTimesToExtendedString() );
               else
                  node.setText( 0, frameGroup.exposureTimesToExtendedString() + " (" + frameGroup.fileItems.length + " frames)" );
               node.nodeData_type = "FrameGroup";
               node.nodeData_indexes = [ i ];
               treeNode[ nodeKey ] = {};
               treeNode[ nodeKey ].node = node;
               treeNode[ nodeKey ].inexes = [ i ];
               treeNode = treeNode[ nodeKey ];
            }
            else
            {
               treeNode = treeNode[ nodeKey ];
               node = treeNode.node;
               node.nodeData_indexes.push( i );
            }
         }

         if ( keywords.length > 0 )
         {
            // all groups are grouped by keywords
            let keywordsString = frameGroup.keywordsToString();
            nodeKey += "_" + keywordsString;
            if ( !treeNode.hasOwnProperty( nodeKey ) )
            {
               node = new TreeBoxNode( node );
               node.expanded = true;
               node.useRichText = true;
               let title = ( keywordsString.length > 0 ) ? keywordsString : "[no matching keywords]";
               node.setText( 0, title + " (" + frameGroup.fileItems.length + " frames)" );
               node.nodeData_type = "FrameGroup";
               node.nodeData_indexes = [ i ];
               treeNode[ nodeKey ] = {};
               treeNode[ nodeKey ].node = node;
               treeNode[ nodeKey ].inexes = [ i ];
               treeNode = treeNode[ nodeKey ];
            }
            else
            {
               treeNode = treeNode[ nodeKey ];
               node = treeNode.node;
               node.nodeData_indexes.push( i );
            }
         }

         let rootNode = node;

         for ( let j = 0; j < frameGroup.fileItems.length; ++j )
         {
            let fileItem = frameGroup.fileItems[ j ];

            let node = new TreeBoxNode( rootNode );
            node.setText( 0, File.extractNameAndExtension( fileItem.filePath ) );

            let toolTip = "<p style=\"white-space:pre;\">" + fileItem.filePath;
            if ( fileItem.exposureTime > 0.004999 )
               toolTip += format( "<br/>Exposure: %.2f s", fileItem.exposureTime );
            toolTip += "</p>";
            node.setToolTip( 0, toolTip );

            if ( j === 0 && frameGroup.hasMaster )
            {
               node.setIcon( 0, this.masterFrameIcon );
               let f = node.font( 0 );
               f.bold = true;
               node.setFont( 0, f );
            }
            else switch ( frameGroup.imageType )
            {
               case ImageType.Bias:
               case ImageType.Dark:
               case ImageType.Flat:
                  node.setIcon( 0, this.calibrationFrameIcon );
                  break;
               case ImageType.Light:
                  node.setIcon( 0, this.lightFrameIcon );
                  break;
            }

            // fill solver data for light frames
            if ( engine.showAstrometricInfo )
            {
               if ( frameGroup.imageType == ImageType.Light )
               {
                  for ( let k = 1; k <= 5; ++k )
                  {
                     node.setText( k, "-" );
                     node.setAlignment( k, Alignment.Center );
                  }

                  if ( fileItem.hasOwnProperty( "solverParams" ) )
                  {
                     node.setText( 1, fileItem.solverParams.observationDate );

                     if ( !isNaN( fileItem.solverParams.ra ) )
                     {
                        let ra = DMSangle.FromAngle( fileItem.solverParams.ra / 15 );
                        node.setText( 2, ra.ToString( true /* hours */ ) );
                     }
                     if ( !isNaN( fileItem.solverParams.dec ) )
                     {
                        let dec = DMSangle.FromAngle( fileItem.solverParams.dec );
                        node.setText( 3, dec.ToString() );
                     }

                     if ( !isNaN( fileItem.solverParams.focalLength ) )
                        node.setText( 4, format( "%.2f", fileItem.solverParams.focalLength ) );
                     if ( !isNaN( fileItem.solverParams.pixelSize ) )
                        node.setText( 5, format( "%.2f", fileItem.solverParams.pixelSize ) );
                  }
               }
            }

            node.nodeData_type = "FileItem";
            node.nodeData_itemIndex = j;
            node.nodeData_groupIndex = i;
            node.nodeData_filePath = fileItem.filePath;
         }

         // adjust columns
         let lightsTree = this.tabBox.pageControlByIndex( BPP.imageTypeIndex( ImageType.Light ) ).treeBox;
         for ( let i = 0; i < lightsTree.numberOfColumns; ++i )
            lightsTree.adjustColumnWidthToContents( i );
      }

      // once tree boxes has been refreshed the calibration panel should be updated
      this.calibrationPanelPreProcess.updateContent();
      this.calibrationPanelPostProcess.updateContent();
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-GUI.js - Released 2026-05-10T11:05:00Z
