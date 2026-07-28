// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-LNReferenceSelector.js - Released 2026-05-10T11:05:00Z
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

#include <pjsr/controls/ImageView.js>

/**
 * This control manages the list of files, the corresponding state and measurements
 * and handles the interaction events.
 *
 */
var WBPPLNFilesTable = class extends Control
{
   constructor( parent )
   {
      super( parent );

      this.framesTree = new TreeBox( this );
      this.framesTree.alternateRowColor = true;
      this.framesTree.onCurrentNodeUpdated = ( node ) =>
      {
         // the case where no node is selected is not handled since this case should never occur.
         if ( node )
            this.onFrameSelection( node.__activeFrame__ );
      };

      // sizers

      this.sizer = new VerticalSizer;
      this.sizer.add( this.framesTree );

      //

      this.activeFrames = []; // the list of frames of the group
      this.bestFrames = {}; // the single best frame or the set of best frames depending on the reference frame generation mode
      this.selectedFrame = undefined; // the file path of the currently selected frame
      this.STFReference = undefined; // the file path of the file used for the current STF transformation
      this.STFLocked = false; // FALSE if STF parameters are updated on frame selection, TRUE if STF is freezed

      // work methods

      let numberOfDigits = function( value )
      {
         if ( value <= 0 ) return 3;
         let xlog = Math.log10( value );
         let maxDecimalDigits = 3;
         let retVal;
         if ( xlog < 0 )
            retVal = Math.floor( -xlog ) + maxDecimalDigits;
         else
         {
            let N = Math.floor( xlog );
            retVal = Math.max( 0, maxDecimalDigits - N );
         }
         return retVal;
      }

      let formatFloat = function( value, digits )
      {
         return format( "%0." + digits + "f", value );
      }

      this.columnsDescriptor = [
      {
         label: "STF #",
         alignment: TextAlignment.Right,
         content: ( activeFrame, i ) =>
         {
            return " " + i;
         }
      },
      {
         label: "Best",
         alignment: TextAlignment.Center,
         content: () =>
         {
            return "";
         }
      },
      {
         label: "File name",
         alignment: TextAlignment.Left,
         toolTip: ( activeFrame ) => ( activeFrame.current ),
         content: ( activeFrame ) =>
         {
            return File.extractNameAndExtension( activeFrame.current )
         }
      },
      {
         label: "PSF SW",
         alignment: TextAlignment.Right,
         nDigits: () => ( Math.max.apply( null, this.activeFrames.map( f => numberOfDigits( f.descriptor.PSFSignalWeight ) ) ) ),
         content: ( activeFrame, i, N ) => ( formatFloat( activeFrame.descriptor.PSFSignalWeight, N ) ),
         associatedMetric: BPP.LocalNormalizationRefFrameMetric.PSFSW

      },
      {
         label: "PSF SNR",
         alignment: TextAlignment.Right,
         nDigits: () => ( Math.max.apply( null, this.activeFrames.map( f => numberOfDigits( f.descriptor.SNR ) ) ) ),
         content: ( activeFrame, i, N ) => ( formatFloat( activeFrame.descriptor.SNR, N ) ),
         associatedMetric: BPP.LocalNormalizationRefFrameMetric.PSFSNR
      },
      {
         label: "M*",
         alignment: TextAlignment.Right,
         nDigits: () => ( Math.max.apply( null, this.activeFrames.map( f => numberOfDigits( f.descriptor.Mstar ) ) ) ),
         content: ( activeFrame, i, N ) => ( formatFloat( activeFrame.descriptor.Mstar, N ) ),
         associatedMetric: BPP.LocalNormalizationRefFrameMetric.MSTAR
      },
      {
         label: "Median",
         alignment: TextAlignment.Right,
         nDigits: () => ( Math.max.apply( null, this.activeFrames.map( f => numberOfDigits( f.descriptor.median ) ) ) ),
         content: ( activeFrame, i, N ) => ( formatFloat( activeFrame.descriptor.median, N ) ),
         associatedMetric: BPP.LocalNormalizationRefFrameMetric.MEDIAN
      },
      {
         label: "# stars",
         alignment: TextAlignment.Right,
         content: ( activeFrame ) => ( "" + activeFrame.descriptor.numberOfStars ),
         associatedMetric: BPP.LocalNormalizationRefFrameMetric.STARS
      },
      {
         label: "", // dummy column for layout purposes
         alignment: TextAlignment.Right,
         content: () => ( "" )
      } ]

      this.onReturn = function( retVal )
      {
         // clean up
         this.preview.reset();
         this.removeIntegratedImagesFromDisk( this.referenceFrame || "" /* except the best reference frame */ );
         this.saveCache();
      };

      // init
      this.clearAutostretchReference();
      this.setHeaders();
   }

   /**
    * Node selection handler. This function must be invoked when the current node tree changes because of the user interacting
    * with the treeBox or when a node is programmatically selected.
    *
    * @param {*} activeFrame
    */
   onFrameSelection( activeFrame )
   {
      this.selectedFrame = activeFrame;
      if ( !this.STFLocked )
      {
         this.STFReference = this.selectedFrame;
         this.updateSTFReferenceIcon();
      }
      if ( this.onFrameSelected )
         this.onFrameSelected( activeFrame );
   }

   /** Sets the tree header labels, alignments and sort icons from the columns descriptor. */
   setHeaders()
   {
      for ( let i = 0; i < this.columnsDescriptor.length; ++i )
      {
         this.framesTree.setHeaderText( i, this.columnsDescriptor[ i ].label );
         this.framesTree.setHeaderAlignment( i, this.columnsDescriptor[ i ].alignment );
         if ( this.columnsDescriptor[ i ].associatedMetric !== undefined
           && this.columnsDescriptor[ i ].associatedMetric == engine.localNormalizationBestReferenceSelectionMethod )
            this.framesTree.setHeaderIcon( i, this.scaledResource( ":/icons/sort-down.png" ) )
         else
            this.framesTree.setHeaderIcon( i, null )
      }
   }

   /** Rebuilds the entire tree content from the current active frames and best frames lists. */
   updateContent()
   {
      let treeBox = this.framesTree;
      let frames = this.activeFrames;
      let best = this.bestFrames;

      treeBox.clear();
      this.setHeaders();

      // prepare the number of digits for each column
      let digits = [];
      for ( let i = 0; i < this.columnsDescriptor.length; i++ )
         digits[ i ] = this.columnsDescriptor[ i ].nDigits ? this.columnsDescriptor[ i ].nDigits() : 0;

      for ( let i = 0; i < frames.length; i++ )
      {
         let node = new TreeBoxNode();
         node.__activeFrame__ = frames[ i ];
         node.__index__ = i;
         let isIntegrated = node.__activeFrame__.__integrated__;

         // cell contents
         for ( let j = 0; j < this.columnsDescriptor.length; j++ )
         {
            node.setText( j, this.columnsDescriptor[ j ].content( frames[ i ], i, digits[ j ] ) )
            node.setAlignment( j, this.columnsDescriptor[ j ].alignment );
            // tooltips
            if ( this.columnsDescriptor[ j ].toolTip )
               node.setToolTip( j, this.columnsDescriptor[ j ].toolTip( frames[ i ] ) );
         }

         // fill the Best column icons

         if ( isIntegrated )
            node.setIcon( 1, this.scaledResource( ":/icons/ok-button.png" ) );
         else if ( node.__activeFrame__.__disabled__ )
            node.setIcon( 1, this.scaledResource( ":/browser/disabled.png" ) );
         else if ( best[ node.__activeFrame__.current ] )
            node.setIcon( 1, this.scaledResource( ":/browser/enabled.png" ) );

         treeBox.add( node );

         if ( this.selectedFrame !== undefined )
            if ( frames[ i ].current == this.selectedFrame.current )
               treeBox.currentNode = node;
      }

      this.updateSTFReferenceIcon();

      // initially update the column widths
      if ( this.treeInitialized == undefined )
      {
         this.treeInitialized = true;
         this.makeAllBold();
         for ( let j = 0; j < this.columnsDescriptor.length; j++ )
            treeBox.adjustColumnWidthToContents( j );
         this.makeAllBold( false );
      }

      this.setFonts();
      this.updateMetricColumnWidth();
   }

   /** Updates the STF reference icon on the tree nodes to highlight the current STF reference frame. */
   updateSTFReferenceIcon()
   {
      for ( let i = 0; i < this.framesTree.numberOfChildren; i++ )
      {
         let node = this.framesTree.child( i );
         if ( this.STFReference != undefined && node.__activeFrame__.current == this.STFReference.current )
            node.setIcon( 0, this.scaledResource( ":/toolbar/image-stf-auto.png" ) );
         else
            node.clearIcon( 0 );
      }
      this.framesTree.adjustColumnWidthToContents( 0 );
   }

   /** Adjusts column widths for metric columns to fit their content. */
   updateMetricColumnWidth()
   {
      for ( let j = 0; j < this.columnsDescriptor.length; j++ )
         if ( this.columnsDescriptor[ j ].associatedMetric !== undefined )
            this.framesTree.adjustColumnWidthToContents( j );
   }

   /**
    * Sets or clears bold styling on all columns of all tree nodes.
    *
    * @param {boolean} bold true to set bold, false to clear it (defaults to true)
    */
   makeAllBold( bold )
   {
      for ( let i = 0; i < this.framesTree.numberOfChildren; i++ )
      {
         let node = this.framesTree.child( i );
         for ( let j = 0; j < this.columnsDescriptor.length; j++ )
            this.makeColumnBold( node, j, ( bold != undefined ? bold : true ) );
      }
   }

   /**
    * Sets or clears bold styling on a specific column of a tree node.
    *
    * @param {TreeBoxNode} node the tree node
    * @param {number} i the column index
    * @param {boolean} bold true to set bold, false to clear it
    */
   makeColumnBold( node, i, bold )
   {
      let font = node.font( i );
      font.bold = ( bold != undefined ? bold : true );
      node.setFont( i, font );
   }

   /**
    * Sets or clears italic styling on a specific column of a tree node.
    *
    * @param {TreeBoxNode} node the tree node
    * @param {number} i the column index
    * @param {boolean} italic true to set italic, false to clear it
    */
   makeColumnItalic( node, i, italic )
   {
      let font = node.font( i );
      font.italic = ( italic != undefined ? italic : true );
      node.setFont( i, font );
   }

   /** Applies font styling (bold, italic, color) to tree nodes based on metric, integrated and best status. */
   setFonts()
   {
      for ( let i = 0; i < this.framesTree.numberOfChildren; i++ )
      {
         let node = this.framesTree.child( i );

         // metric column
         for ( let j = 0; j < this.columnsDescriptor.length; j++ )
            if ( this.columnsDescriptor[ j ].associatedMetric != undefined && this.columnsDescriptor[ j ].associatedMetric == engine.localNormalizationBestReferenceSelectionMethod )
            {
               this.makeColumnBold( node, j )
               node.setTextColor( j, 0x000000FF )
            }

         // integrated frames
         if ( node.__activeFrame__.__integrated__ != undefined )
            for ( let j = 0; j < this.columnsDescriptor.length; j++ )
               this.makeColumnItalic( node, j )

         // best frames
         if ( this.bestFrames[ node.__activeFrame__.current ] )
            for ( let j = 0; j <= 2; j++ )
               this.makeColumnBold( node, j );
      }
   }

   /**
    * Assigns the active and best frames lists and refreshes the tree content.
    *
    * @param {Array} activeFrames the list of active frames
    * @param {Array} bestFrames the list of best frames
    */
   setFrames( activeFrames, bestFrames )
   {
      if ( activeFrames )
         this.activeFrames = activeFrames;
      if ( bestFrames )
         this.bestFrames = bestFrames.reduce( ( acc, item ) =>
         {
            acc[ item.current ] = true;
            return acc;
         },
         {} );
      this.updateContent();
   }

   /**
    * Programmatically selects a frame and refreshes the tree.
    *
    * @param {*} frame the frame to select
    */
   selectFrame( frame )
   {
      this.selectedFrame = frame;
      if ( !this.STFLocked )
         this.STFReference = this.selectedFrame;
      this.updateContent();
   }

   /** Locks the current autoStretch STF reference so it does not change on frame selection. */
   lockAutostretchReference()
   {
      this.STFLocked = true;
   }

   /** Unlocks the autoStretch STF reference and resets it to the currently selected frame. */
   clearAutostretchReference()
   {
      this.STFLocked = false;
      this.STFReference = this.selectedFrame;
      this.updateSTFReferenceIcon();
   }
};

/**
 * This control shows the assigned bmp image and allows to scroll and zoom in/out.
 *
 * @param {*} parent
 */
var WBPPLNPreview = class extends Control
{
   constructor( parent )
   {
      super( parent );

      // autoStretch option, if true the current autoStretch will update accordingly to the set image
      this.autoStretch = true;
      // the current active frame shown
      this.dummyActiveFrame = {
         current: "",
         descriptor:
         {
            median: 0.1,
            mad: 0.1
         }
      };
      // the current STF to be applied to the set image
      this.currentSTF = [
         [ 0.5, 0, 1, 0, 1 ],
         [ 0.5, 0, 1, 0, 1 ],
         [ 0.5, 0, 1, 0, 1 ],
         [ 0.5, 0, 1, 0, 1 ],
         [ 0.5, 0, 1, 0, 1 ]
      ];
      // map between file paths and windows
      this.windows = {};
      // STF cache
      this.autoStretchCache = {};
      // multiplicative coefficient of the c0 term in STF
      this.c0Coeff = 0;
      // multiplicative coefficient of the m term in STF
      this.mCoeff = 0;

      //

      this.preview = new ImageView( this );

      //

      this.sizer = new HorizontalSizer;
      this.sizer.add( this.preview );

      // Preview extra controls

      this.lockSTFCheckbox = new CheckBox( this.preview );
      this.lockSTFCheckbox.text = "Lock stretch";
      this.lockSTFCheckbox.checked = true;
      this.lockSTFCheckbox.adjustToContents();
      this.lockSTFCheckbox.setFixedWidth( this.lockSTFCheckbox.width );
      this.lockSTFCheckbox.onCheck = ( checked ) =>
      {
         this.autoStretch = !checked;
         this.set( this.dummyActiveFrame );
         if ( this.onLockStretchChange )
            this.onLockStretchChange( checked );
      };
      this.preview.appendTopControl( this.lockSTFCheckbox );

      // AutoStretch adjustments

      let adjustmentsParent = new Control( this.preview );
      adjustmentsParent.sizer = new HorizontalSizer;
      adjustmentsParent.sizer.spacing = 4;

      this.c0StretchCoeffNumericControl = new NumericControl( adjustmentsParent );
      this.c0StretchCoeffNumericControl.label.text = "Shadows";
      this.c0StretchCoeffNumericControl.setRange( -1, 1 );
      this.c0StretchCoeffNumericControl.slider.setRange( 0, 100000 );
      this.c0StretchCoeffNumericControl.slider.setFixedWidth( 280 );
      this.c0StretchCoeffNumericControl.edit.visible = false;
      this.c0StretchCoeffNumericControl.setPrecision( 5 );
      this.c0StretchCoeffNumericControl.setValue( 0 );
      this.c0StretchCoeffNumericControl.slider.onMousePress = () =>
      {
         this.c0StretchCoeffNumericControl.mouseDownValue = this.c0StretchCoeffNumericControl.value;
      };
      this.c0StretchCoeffNumericControl.slider.onMouseRelease = () =>
      {
         if ( this.c0StretchCoeffNumericControl.mouseDownValue != this.c0StretchCoeffNumericControl.value )
         {
            this.c0Coeff = Math.pow( this.c0StretchCoeffNumericControl.value, 5 );
            this.set( this.dummyActiveFrame );
         }
      };

      this.mStretchCoeffNumericControl = new NumericControl( adjustmentsParent );
      this.mStretchCoeffNumericControl.label.text = "Midtones";
      this.mStretchCoeffNumericControl.setRange( -1, 1 );
      this.mStretchCoeffNumericControl.slider.setRange( 0, 100000 );
      this.mStretchCoeffNumericControl.slider.setFixedWidth( 280 );
      this.mStretchCoeffNumericControl.edit.visible = false;
      this.mStretchCoeffNumericControl.setPrecision( 5 );
      this.mStretchCoeffNumericControl.setValue( 0 );
      this.mStretchCoeffNumericControl.slider.onMousePress = () =>
      {
         this.mStretchCoeffNumericControl.mouseDownValue = this.mStretchCoeffNumericControl.value;
      };
      this.mStretchCoeffNumericControl.slider.onMouseRelease = () =>
      {
         if ( this.mStretchCoeffNumericControl.mouseDownValue != this.mStretchCoeffNumericControl.value )
         {
            this.mCoeff = Math.pow( this.mStretchCoeffNumericControl.value, 5 );
            this.set( this.dummyActiveFrame );
         }
      };

      this.c0Reset = new PushButton( this.preview );
      this.c0Reset.text = "Reset"
      this.c0Reset.toolTip = "<p>Resets the shadows adjustment.</p>"
      this.c0Reset.onClick = () =>
      {
         this.c0StretchCoeffNumericControl.setValue( 0 );
         this.c0Coeff = 0;
         this.set( this.dummyActiveFrame );
      };

      this.mReset = new PushButton( this.preview );
      this.mReset.text = "Reset"
      this.mReset.toolTip = "<p>Resets the midtones adjustment.</p>"
      this.mReset.onClick = () =>
      {
         this.mStretchCoeffNumericControl.setValue( 0 );
         this.mCoeff = 0;
         this.set( this.dummyActiveFrame );
      };

      this.autoStretchOngoingLabel = new Label( adjustmentsParent );
      this.autoStretchOngoingLabel.useRichText = true;
      this.autoStretchOngoingLabel.textAlignment = TextAlignment.VertCenter | TextAlignment.Left;

      this.autoStretchOngoingIcon = new ToolButton( adjustmentsParent );
      this.autoStretchOngoingIcon.setScaledFixedSize( 20, 20 );
      this.autoStretchOngoingIcon.icon = this.scaledResource( ":/icons/clock.png" );

      let autoStretchOngoingSizer = new HorizontalSizer;
      autoStretchOngoingSizer.spacing = 4;
      autoStretchOngoingSizer.add( this.autoStretchOngoingIcon );
      autoStretchOngoingSizer.add( this.autoStretchOngoingLabel );

      let resetButtonsSizer = new VerticalSizer;
      resetButtonsSizer.spacing = 4;
      resetButtonsSizer.add( this.c0Reset );
      resetButtonsSizer.add( this.mReset );

      let adjustmentsSizer = new VerticalSizer;
      adjustmentsSizer.spacing = 4;
      adjustmentsSizer.add( this.c0StretchCoeffNumericControl );
      adjustmentsSizer.add( this.mStretchCoeffNumericControl );

      adjustmentsParent.sizer.add( adjustmentsSizer );
      adjustmentsParent.sizer.add( resetButtonsSizer );
      adjustmentsParent.sizer.addSpacing( 8 );
      adjustmentsParent.sizer.add( autoStretchOngoingSizer );
      adjustmentsParent.sizer.addStretch();

      this.preview.appendBottomControl( adjustmentsParent );

      this.updateContent();
   }

   /** Displays the file name of the given active frame in the status bar. */
   setStatusActiveFrameInfo( activeFrame )
   {
      this.setStatusMessage( "<b>" + File.extractNameAndExtension( activeFrame.current ) + "</b>" );
   }

   /** Sets a rich-text status message in the preview control status bar. */
   setStatusMessage( message )
   {
      this.preview.setStatusMessage( message );
   }

   /**
    * Sets and displays the given active frame, applying AutoStretch if enabled.
    *
    * @param {*} activeFrame the frame to display
    */
   set( activeFrame )
   {
      this.dummyActiveFrame.current = activeFrame.current;
      this.dummyActiveFrame.descriptor = activeFrame.descriptor;

      // We first get the mapped window (load from disk if needed).
      let window = this.getWindow( this.dummyActiveFrame.current );
      if ( window === null )
         return;

      this.autoStretchOngoingLabel.text = "<b>Stretching...</b>";
      this.autoStretchOngoingIcon.visible = true;
      CoreApplication.processEvents();

      // Compute STF AutoStretch or retrieve it from the cache.
      let cacheKey = this.dummyActiveFrame.current + "_" + this.c0Coeff + "_" + this.mCoeff;
      if ( this.autoStretch )
         if ( this.autoStretchCache[ cacheKey ] !== undefined )
            this.currentSTF = this.autoStretchCache[ cacheKey ];
         else
         {
            this.currentSTF = WBPPUtils.computeSTFAutoStretch( window.mainView, this.dummyActiveFrame.descriptor,
                                                               -this.c0Coeff, -this.mCoeff );
            this.autoStretchCache[ cacheKey ] = this.currentSTF;
         }

      // Apply STF AutoStretch and update the preview.
      let image = new Image( window.mainView.image );
      image.applyDisplayFunction( this.currentSTF );
      let bmp = image.render();
      if ( this.preview.isValid )
         this.preview.regenerate( image.render() );
      else
      {
         this.preview.setImage( image.render() );
         this.preview.zoomToFit();
      }
      image.free();

      this.autoStretchOngoingLabel.clear();
      this.autoStretchOngoingIcon.visible = false;
   }

   /**
    * Synchronizes the lock stretch checkbox with the current autoStretch state.
    */
   updateContent()
   {
      this.lockSTFCheckbox.checked = !this.autoStretch;
   }

   /**
    * Returns the ImageWindow for the given file path, opening and caching it if needed.
    *
    * @param {string} filePath the image file path
    * @return {ImageWindow|null}
    */
   getWindow( filePath )
   {
      // return the window if already cached
      if ( this.windows[ filePath ] )
         return this.windows[ filePath ];

      // we are interested only in the first window in case the file contains multiple windows
      let windows = ImageWindow.open( filePath );
      if ( !windows || windows.length == 0 )
         return null;
      for ( let i = 1; i < windows.length; i++ )
         windows[ i ].forceClose();
      this.windows[ filePath ] = windows[ 0 ];
      return windows[ 0 ];
   }

   /** Clears the BMP cache and closes all opened image windows. */
   clear()
   {
      let keys = Object.keys( this.windows );
      for ( let i = 0; i < keys.length; i++ )
         this.windows[ keys[ i ] ].forceClose();
   }
};

/**
 * Dialog for interactive selection of the Local Normalization reference frame.
 * Allows the user to inspect, blink, exclude frames, and optionally integrate
 * the best frames to generate a reference image candidate.
 *
 * @param {FrameGroup} frameGroup the frame group to select the reference from
 */
var WBPPLocalNormalizationReferenceSelector = class extends Dialog
{
   constructor( frameGroup )
   {
      super();

      this.frameGroup = frameGroup;
      this.windowTitle = "Local Normalization Selector";
      this.spacing = 8;

      this.initialSizeAndPos();

      // local normalization parameters

      // NOTE: we set this control to work in interactive mode, this way the option "Interactive"
      // is not be listed and only single best or integrate best frames are selectable.
      // We assign the default value to the reference frame generation method.
      this.localNormalizationParametersControl = new LocalNormalizationControl( this, false, true /* forInteractiveMode */ );

      // backup the Local Normalization parameters and
      this.localNormalizationParametersControl.updateControls();
      this.localNormalizationParametersControl.onReferenceFrameGenerationChange = () =>
      {
         // updates the best frames keeping the excluded frames
         let currentFrame = this.framesTable.selectedFrame;
         this.resetBestFrames( true /* resetN */ );
         this.updateContent();
         this.selectFrame( currentFrame );
      };
      this.localNormalizationParametersControl.onEvaluationCriteriaChanged = () =>
      {
         // updates the best frames keeping the excluded frames
         let currentFrame = this.framesTable.selectedFrame;
         this.resetBestFrames();
         this.updateContent();
         this.selectFrame( currentFrame );
      };
      this.localNormalizationParametersControl.adjustToContents();

      // Main Label
      this.mainTitleLabel = new Label( this );
      this.mainTitleLabel.useRichText = true;
      this.mainTitleLabel.textAlignment = TextAlignment.Center;
      this.mainTitleLabel.styleSheet = this.scaledStyleSheet(
         "QWidget#" + this.mainTitleLabel.uniqueId + " {"
         + "font-size: 11pt;"
         + "border-style: solid;"
         + "border-color: #aaaaaa;"
         + "border-width: 1pt;"
         + "padding: 0.5em;"
         + "}" );

      // FILE LIST CONTROL

      // file tree
      this.framesTable = new WBPPLNFilesTable( this );
      this.framesTable.onFrameSelected = ( activeFrame ) =>
      {
         this.preview.set( activeFrame );
         this.preview.setStatusActiveFrameInfo( activeFrame );
         this.updateWithSelectedFrame();
      };

      // CENTRAL CONTROLS

      let separator = () =>
      {
         let control = new Control( this );
         control.styleSheet = this.scaledStyleSheet(
            "QWidget#" + control.uniqueId + " {"
            + "border-style: solid;"
            + "border-color: #aaaaaa;"
            + "border-width: 1pt;"
            + "}" );
         control.setFixedHeight( 1 );
         control.setVariableWidth();
         return control;
      };

      this.resetButton = new PushButton( this );
      this.resetButton.text = " Reset";
      this.resetButton.toolTip = "<p>Resets the frames table and sets the number of best frames to be integrated "
         + "to the suggested value.</p>"
      this.resetButton.icon = this.scaledResource( ":/icons/reload.png" );
      this.resetButton.onClick = () =>
      {
         // Re-enable all frames, reload data, select the first frame
         try
         {
            this.enableAllFrames();
            this.resetBestFrames( true /* resetN */ , false /* remove integrated */ )
            this.updateContent();
            this.selectFirstFrame();
         }
         catch ( e )
         {
            console.noteln( e )
         }
      };

      //

      this.excludeFrameButton = new PushButton( this );
      this.excludeFrameButton.text = " Exclude";
      this.excludeFrameButton.toolTip = "<p>Exclude or re-include the selected frame.</p>"
         + "<p>By excluding a frame, we ensure that it is never selected as either the single best reference frame or "
         + "as part of the frames that will be integrated to generate the normalization reference image.</p>"
      this.excludeFrameButton.icon = this.scaledResource( ":/file-explorer/delete.png" );
      this.excludeFrameButton.onClick = () =>
      {
         // enable/disable the current frame, recompute the best frames
         this.switchFrameActivationStatus( this.framesTable.selectedFrame );
         this.updateBestFrames();
         this.updateContent();
      };

      //

      let numberOfFramesToolTip = "<p>The number of frames to integrate.</p>"
         + "<p>This control is relevant only when the reference frame is generated by integrating the best frames.</p>";
      this.numberOfFramesLabel = new Label( this );
      this.numberOfFramesLabel.text = "Frames:"
      this.numberOfFramesLabel.toolTip = numberOfFramesToolTip;
      this.numberOfFramesLabel.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
      this.numberOfFramesSpinBox = new SpinBox( this );
      this.numberOfFramesSpinBox.minValue = 3;
      this.numberOfFramesSpinBox.maxValue = 3;
      this.numberOfFramesSpinBox.toolTip = numberOfFramesToolTip;
      this.numberOfFramesSpinBox.onValueUpdated = ( value ) =>
      {
         this.N = value;
         this.updateBestFrames();
         this.updateContent();
      };
      this.numberOfFramesSpinBox.updateContent = () =>
      {
         this.numberOfFramesSpinBox.enabled = this.N >= 3 && engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.INTEGRATION_BEST_FRAMES;
         this.numberOfFramesSpinBox.maxValue = this.activeFrames.length;
         if ( !this.numberOfFramesSpinBox.enabled )
         {
            this.numberOfFramesSpinBox.minValue = 1;
            this.numberOfFramesSpinBox.value = 1;
         }
         else
         {
            this.numberOfFramesSpinBox.minValue = 3;
            this.numberOfFramesSpinBox.value = this.N;
         }
      };

      // blink animation

      this.backButton = new ToolButton( this );
      this.backButton.icon = this.scaledResource( ":/icons/step-backward.png" );
      this.backButton.setScaledFixedSize( 24, 24 );
      this.backButton.toolTip = "<p>Previous frame</p>"
      this.backButton.onMousePress = () =>
      {
         this.selectNextBestFrame( false /* forward */ );
      };

      this.playButton = new ToolButton( this );
      this.playButton.icon = this.scaledResource( ":/icons/play.png" );
      this.playButton.setScaledFixedSize( 24, 24 );
      this.playButton.toolTip = "<p>Play</p>"
      this.playButton.onMousePress = () =>
      {
         if ( this.blinkAnimationTimer == undefined )
         {
            this.startBlinkingAnimation( 0.5 );
            this.playButton.icon = this.scaledResource( ":/icons/stop.png" );
            this.playFastButton.enabled = false;
         }
         else
         {
            this.stopBlinkingAnimation()
            this.playButton.icon = this.scaledResource( ":/icons/play.png" );
            this.playFastButton.enabled = true;
         }
         this.updateWithTimer();
      };

      this.playFastButton = new ToolButton( this );
      this.playFastButton.icon = this.scaledResource( ":/icons/forward.png" );
      this.playFastButton.setScaledFixedSize( 24, 24 );
      this.playFastButton.toolTip = "<p>Play fast</p>"
      this.playFastButton.onMousePress = () =>
      {
         if ( this.blinkAnimationTimer == undefined )
         {
            this.startBlinkingAnimation( 0.05 );
            this.playFastButton.icon = this.scaledResource( ":/icons/stop.png" );
            this.playButton.enabled = false;
         }
         else
         {
            this.stopBlinkingAnimation()
            this.playFastButton.icon = this.scaledResource( ":/icons/forward.png" );
            this.playButton.enabled = true;
         }
         this.updateWithTimer();
      };

      this.forwardButton = new ToolButton( this );
      this.forwardButton.icon = this.scaledResource( ":/icons/step-forward.png" );
      this.forwardButton.setScaledFixedSize( 24, 24 );
      this.forwardButton.toolTip = "<p>Next frame</p>"
      this.forwardButton.onMousePress = () =>
      {
         this.selectNextBestFrame( true /* forward */ );
      };

      this.blinkBestCheckBox = new CheckBox( this );
      this.blinkBestCheckBox.text = "Best frames";
      this.blinkBestCheckBox.toolTip = "<p>If checked, the blink buttons loop through the set of best frames only.</p>"
      this.blinkBestCheckBox.textAlignment = TextAlignment.Center;
      this.blinkBestCheckBox.checked = true;
      this.blinkBestCheckBox.onCheck = ( checked ) =>
      {
         this.bestFramesOnly = checked;
      };
      this.bestFramesOnly = true;

      let blinkButtonsSizer = new HorizontalSizer;
      blinkButtonsSizer.add( this.backButton )
      blinkButtonsSizer.add( this.playButton )
      blinkButtonsSizer.add( this.playFastButton )
      blinkButtonsSizer.add( this.forwardButton )

      let blinkSizer = new VerticalSizer;
      blinkSizer.add( blinkButtonsSizer );
      blinkSizer.addSpacing( 4 );
      blinkSizer.add( this.blinkBestCheckBox );

      //

      this.generateButton = new PushButton( this );
      this.generateButton.text = "Generate";
      this.generateButton.toolTip = "<p>Runs the integration of the current best frames to generate a local normalization "
         + "reference image candidate.</p>"
         + "<p>The integration is performed applying the additive+scaling global output normalization.</p>"
         + "<p>For pixel rejection, local normalization is applied to the subset of best frames with the single best frame as "
         + "normalization reference.</p>"
      this.generateButton.onClick = () =>
      {
         this.generateReferenceFrame();
      };

      //

      this.proceedButton = new PushButton( this );
      this.proceedButton.text = "Select";
      this.proceedButton.toolTip = "<p>Select the current active frame as the reference and continue.</p>";
      this.proceedButton.onClick = () =>
      {
         // exit and select the current frame as reference
         this.referenceFrame = this.framesTable.selectedFrame.current;
         this.ok();
      };

      // preview control

      this.preview = new WBPPLNPreview( this );
      this.preview.onLockStretchChange = ( checked ) =>
      {
         if ( checked )
            this.framesTable.lockAutostretchReference();
         else
            this.framesTable.clearAutostretchReference();
         this.preview.c0StretchCoeffNumericControl.enabled = !checked;
         this.preview.mStretchCoeffNumericControl.enabled = !checked;
         this.preview.c0Reset.enabled = !checked;
         this.preview.mReset.enabled = !checked;
      };
      //
      let numberOfFramesSizer = new HorizontalSizer;
      numberOfFramesSizer.spacing = this.spacing;
      numberOfFramesSizer.add( this.numberOfFramesLabel );
      numberOfFramesSizer.add( this.numberOfFramesSpinBox );

      let buttonsSizer = new VerticalSizer;
      buttonsSizer.spacing = this.spacing;
      buttonsSizer.add( this.resetButton );
      buttonsSizer.add( separator() );
      buttonsSizer.add( numberOfFramesSizer );
      buttonsSizer.add( this.excludeFrameButton );
      buttonsSizer.add( separator() );
      buttonsSizer.add( blinkSizer );
      buttonsSizer.add( separator() );
      buttonsSizer.add( this.generateButton );
      buttonsSizer.add( this.proceedButton );
      buttonsSizer.addStretch();

      let tableAndControlsSizer = new HorizontalSizer;
      tableAndControlsSizer.spacing = this.spacing;
      tableAndControlsSizer.add( this.framesTable )
      tableAndControlsSizer.add( buttonsSizer )

      let leftSizer = new VerticalSizer;
      leftSizer.spacing = this.spacing;
      leftSizer.addSpacing( 8 );
      leftSizer.add( this.localNormalizationParametersControl );
      leftSizer.add( this.mainTitleLabel );
      leftSizer.add( tableAndControlsSizer );

      //

      this.sizer = new HorizontalSizer;
      this.sizer.margin = this.spacing;
      this.sizer.spacing = this.spacing;
      this.sizer.add( leftSizer );
      this.sizer.add( this.preview );

      this.adjustMaxSizes();

      this.initialize();
   }

   /** Sets the initial window size and position to 90% of the available screen, centered. */
   initialSizeAndPos()
   {
      this.width = this.availableScreenRect.width * 0.9;
      this.height = this.availableScreenRect.height * 0.9;
      let origin = new Point(
         ( this.availableScreenRect.width - this.width ) / 2,
         ( this.availableScreenRect.height - this.height ) / 2 );
      this.move( origin );
   }

   /** Constrains maximum widths of left panel controls based on current window dimensions. */
   adjustMaxSizes()
   {
      // the left column width is given by the current LN control width
      let leftPanelMaxWidth = this.width / 3;

      this.localNormalizationParametersControl.setMaxWidth( leftPanelMaxWidth );
      this.mainTitleLabel.setMaxWidth( leftPanelMaxWidth );

      this.proceedButton.adjustToContents();
      let buttonsMaxWidth = this.proceedButton.width;

      this.resetButton.setMaxWidth( buttonsMaxWidth );
      this.excludeFrameButton.setMaxWidth( buttonsMaxWidth );
      this.numberOfFramesSpinBox.setMaxWidth( buttonsMaxWidth );
      this.generateButton.setMaxWidth( buttonsMaxWidth );
      this.proceedButton.setMaxWidth( buttonsMaxWidth );

      this.framesTable.setMaxWidth( leftPanelMaxWidth - buttonsMaxWidth - this.spacing );
   }

   /**
    * Update the entire window and children controls
    *
    */
   updateContent()
   {
      let lbl = engine.subframeAnalyzer.readableLNReferenceSelectionMethod();

      if ( engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.SINGLE_BEST )
         this.mainTitleLabel.text = "Select the single reference frame with <b>" + lbl + "</b>";
      else
         this.mainTitleLabel.text = "Integrate the frames with <b>" + lbl + "</b>";

      this.preview.updateContent();
      this.framesTable.setFrames( this.activeFrames, this.bestFrames );
      this.updateWithSelectedFrame();
   }

   /**
    * Handles the status of the  controls that depend on the selected frame
    *
    */
   updateWithSelectedFrame()
   {
      let itemSelected = this.framesTable.selectedFrame != undefined
      // disable switch not enabled for integrated frames (only if not blinking)
      if ( this.blinkAnimationTimer == undefined )
      {
         this.excludeFrameButton.enabled = itemSelected && this.framesTable.selectedFrame.__integrated__ == undefined;
         // proceed is enabled only if we have to select a single frame or if we have selected an integrated one
         this.proceedButton.enabled = true;

         let blinkEnabled = engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.INTEGRATION_BEST_FRAMES;
         this.playButton.enabled = blinkEnabled
         this.playFastButton.enabled = blinkEnabled
         this.blinkBestCheckBox.enabled = blinkEnabled
      }
      else
      {
         this.proceedButton.enabled = false;
      }

      if ( itemSelected && this.framesTable.selectedFrame.__disabled__ )
      {
         this.excludeFrameButton.icon = this.scaledResource( ":/browser/enabled.png" );
         this.excludeFrameButton.text = " Include";
      }
      else
      {
         this.excludeFrameButton.icon = this.scaledResource( ":/file-explorer/delete.png" );
         this.excludeFrameButton.text = " Exclude";
      }
   }

   /** Updates control enabled states based on whether a blink animation timer is active. */
   updateWithTimer()
   {
      let enabled = this.blinkAnimationTimer == undefined;

      this.localNormalizationParametersControl.enabled = enabled;
      this.preview.lockSTFCheckbox.enabled = enabled;
      this.resetButton.enabled = enabled;
      this.excludeFrameButton.enabled = enabled;
      this.backButton.enabled = enabled;
      this.generateButton.enabled = enabled;

      this.updateWithSelectedFrame();
   }

   /**
    * Recalculate the best frames list depending on the Local Normalization control parameters.
    *
    * @param {*} resetN true if the current number of best frames has to be reset
    * @param {*} removeIntegrated true if the integrated frames must be removed
    */
   resetBestFrames( resetN, removeIntegrated )
   {
      if ( removeIntegrated != undefined && removeIntegrated )
      {
         // delete the integrated images from disk and filter out them from the list
         this.removeIntegratedImagesFromDisk();
         this.activeFrames = this.activeFrames.filter( f => ( f.__integrated__ == undefined ) );
      }

      // first store the filepaths of the integrated frames
      let integrated = this.activeFrames.reduce( ( acc, f ) =>
      {
         if ( f.__integrated__ )
            acc[ f.current ] = true;
         return acc;
      },
      {} );
      // we compute the selection
      let
      {
         N,
         activeFrames
      } = engine.subframeAnalyzer.sortFramesForLocalNormalizationReference( this.frameGroup.cloneWithActiveItems( this.activeFrames ) );
      if ( resetN )
         this.N = N;
      // mark the integrated frames
      this.activeFrames = activeFrames.map( f =>
      {
         if ( integrated[ f.current ] )
            f.__integrated__ = true;
         return f;
      } )
      this.updateBestFrames();
      this.numberOfFramesSpinBox.updateContent();
   }

   /**
    * Regenerate the list of best frames accordingly to the current frames status and the
    * current number of frames to be marked as best
    */
   updateBestFrames()
   {
      // select the best frames excluding the integrated reference frames (only in integration mode)
      this.bestFrames = new Array;
      for ( let i = 0; i < this.activeFrames.length; i++ )
         if ( this.activeFrames[ i ].__integrated__ == undefined )
         {
            let disabled = this.disabledFrames[ this.activeFrames[ i ].current ];
            this.activeFrames[ i ].__disabled__ = disabled;
            if ( !disabled && this.bestFrames.length < this.N )
            {
               this.activeFrames[ i ].__best__ = true;
               this.bestFrames.push( this.activeFrames[ i ] );
            }
         }

      // once updated we disable the Generate button if less than 3 items are available
      this.generateButton.enabled = this.bestFrames.length >= 3;
   }

   /**
    * Programmatically selects the first frame in the list
    *
    */
   selectFirstFrame()
   {
      this.selectFrame( this.activeFrames[ 0 ] );
   }

   /**
    * Programmatically select the given frame
    *
    * @param {*} frame
    */
   selectFrame( frame )
   {
      this.preview.set( frame );
      this.framesTable.selectFrame( frame );
      this.preview.setStatusActiveFrameInfo( frame );
      this.updateWithSelectedFrame();
   }

   /**
    * Marks all frames as enabled
    *
    */
   enableAllFrames()
   {
      this.disabledFrames = this.activeFrames.reduce( ( acc, item ) =>
      {
         acc[ item.current ] = false;
         return acc;
      },
      {} );
   }

   /**
    * Mark/un-mark a frame as disabled
    *
    * @param {*} frame
    */
   switchFrameActivationStatus( frame )
   {
      this.disabledFrames[ frame.current ] = !this.disabledFrames[ frame.current ];
   }

   /**
    * Generates the integrated reference frame with the current list of best frames.
    *
    */
   generateReferenceFrame()
   {
      this.enabled = false;
      try
      {
         this.preview.setStatusMessage( "<b>GENERATING THE REFERENCE FRAME...</b>" )
         let fname = this.frameGroup.folderName( false /* sanitized */ ) + "_" + this.bestFrames.length + "_of_" + engine.subframeAnalyzer.readableLNReferenceSelectionMethod( true /* sanitized */ );
         let
         {
            lnReferenceFilePath,
            cached
         } = engine.imageProcessor.generateLNReference(
            this.frameGroup,
            this.bestFrames /* use the current best frames for integration */ ,
            false, /* do not log into the process logger */
            fname /* desired file name */
         );
         let cachedSelected = false;
         if ( cached )
         {
            // select the cached reference frame
            for ( let i = 0; i < this.activeFrames.length; i++ )
               if ( this.activeFrames[ i ].current == lnReferenceFilePath )
               {
                  this.selectFrame( this.activeFrames[ i ] );
                  cachedSelected = true;
                  break;
               }
         }
         if ( !cachedSelected )
         {
            this.preview.setStatusMessage( "<b>MEASURING THE REFERENCE FRAME...</b>" );
            let activeFrame = ActiveFrame.dummy( lnReferenceFilePath, this.activeFrames[ 0 ] /* clone data from the first active frame */ );
            activeFrame.__integrated__ = true;
            engine.subframeAnalyzer.computeDescriptors( [ activeFrame ] );
            this.activeFrames.unshift( activeFrame );
            this.updateContent();
            this.selectFrame( activeFrame );
         }
      }
      catch ( error )
      {
         console.criticalln( "*** Error: ", error );
      }
      this.enabled = true;
   }

   /**
    * Programmatically move to the next best frame starting from the selected frame in the frames table
    *
    * @return {*}
    */
   selectNextBestFrame( forward )
   {
      if ( this.selectingBestFrame )
         return;

      this.selectingBestFrame = true;

      if ( this.framesTable.selectedFrame == undefined )
      {
         this.selectFirstFrame();
         this.selectingBestFrame = false;
         return;
      }
      let bestFramesMap = this.bestFrames.reduce( ( acc, item ) =>
      {
         acc[ item.current ] = true;
         return acc;
      },
      {} );

      let currentFound = false;
      let i = 0;
      let count = 0;
      // include a double check on the total amount of iterations in case of issues to avoid
      // an infinite loop
      while ( count < this.activeFrames.length * 2 )
      {
         if ( !currentFound )
         {
            if ( this.activeFrames[ i ].current == this.framesTable.selectedFrame.current )
               currentFound = true;
         }
         else
         {
            let enabled = !this.disabledFrames[ this.activeFrames[ i ].current ];
            if ( enabled )
               if (
                  engine.localNormalizationReferenceFrameGenerationMethod == BPP.LocalNormalizationRefFrameMethod.SINGLE_BEST
                  || !this.bestFramesOnly
                  || ( this.bestFramesOnly && bestFramesMap[ this.activeFrames[ i ].current ] ) )
               {
                  this.selectFrame( this.activeFrames[ i ] )
                  this.selectingBestFrame = false;
                  return;
               }
         }

         i = ( ( i + ( forward ? 1 : this.activeFrames.length - 1 ) ) % this.activeFrames.length );
         count++;
      }

      this.selectingBestFrame = false;
   }

   // ------------------
   // animation handling
   // ------------------

   /**
    * Starts the blink animation with the given period.
    *
    * @param {*} period the time elapsed between the next image
    */
   startBlinkingAnimation( period )
   {
      this.blinkAnimationTimer = new Timer
      this.blinkAnimationTimer.interval = period;
      this.blinkAnimationTimer.periodic = true;
      this.blinkAnimationTimer.dialog = this;
      this.blinkAnimationTimer.onTimeout = () =>
      {
         this.selectNextBestFrame( true /* forward */ );
         // refresh the progress report
         CoreApplication.processEvents();
      };
      this.blinkAnimationTimer.start();
   }

   /**
    * Stops the blink animation.
    *
    */
   stopBlinkingAnimation()
   {
      if ( this.blinkAnimationTimer != undefined )
      {
         this.blinkAnimationTimer.stop();
         this.blinkAnimationTimer = undefined;
      }
   }

   // --------------------
   // best frames handling
   // --------------------

   /**
    * Deleted the integrated images from disk, optionally avoid the deletion of the file provided.
    *
    * @param {*} exceptFramePath the path of the file to keep
    */
   removeIntegratedImagesFromDisk( exceptFramePath )
   {
      if ( exceptFramePath == undefined )
         exceptFramePath = "";
      // clean up
      for ( let i = 0; i < this.activeFrames.length; i++ )
         if ( this.activeFrames[ i ].__integrated__ != undefined
            && this.activeFrames[ i ].__cached__ != true
            && this.activeFrames[ i ].current != exceptFramePath )
            // delete the file
            this.removeImageFromDisk( this.activeFrames[ i ].current );
   }

   /** Removes the given image file from disk. */
   removeImageFromDisk( filePath )
   {
      // delete the file
      File.remove( filePath )
   }

   /** Returns the execution cache key for this dialog session. */
   cacheKey()
   {
      return "LNInteractiveGUI_" + engine.outputDirectory + " - " + this.frameGroup.folderName();
   }

   /** Returns true if a cached session exists for this frame group and output directory. */
   hasCache()
   {
      return engine.executionCache.hasCacheForKey( this.cacheKey() );
   }

   /** Restores the dialog state from the execution cache, including integrated frames and selection. */
   restoreFromCache()
   {
      if ( !this.hasCache() )
         return;

      // add the integrated frames
      let cacheData = engine.executionCache.cacheForKey( this.cacheKey() );

      // select the active selected item
      if ( cacheData.integratedFrames )
      {
         for ( let i = cacheData.integratedFrames.length - 1; i >= 0; i-- )
            if ( File.exists( cacheData.integratedFrames[ i ].current ) )
            {
               this.activeFrames.unshift( cacheData.integratedFrames[ i ] );
               this.activeFrames[ 0 ].__cached__ = true;
            }
      }

      this.updateContent();

      let selected = false;
      if ( cacheData.selectedFrame )
      {
         for ( let i = 0; i < this.activeFrames.length; i++ )
            if ( cacheData.selectedFrame.current == this.activeFrames[ i ].current )
            {
               this.selectFrame( this.activeFrames[ i ] );
               selected = true;
               break;
            }
      }

      if ( !selected )
         this.selectFirstFrame();

   }

   /** Saves the current dialog state (integrated frames, selected frame) to the execution cache. */
   saveCache()
   {

      let cacheKey = this.cacheKey();
      let cacheData = {};
      // save the list of generated frames
      cacheData.integratedFrames = [];
      for ( let i = 0; i < this.activeFrames.length; i++ )
         if ( this.activeFrames[ i ].__integrated__ && File.exists( this.activeFrames[ i ].current ) )
            cacheData.integratedFrames.push( this.activeFrames[ i ] );

      // save the selected frame
      cacheData.selectedFrame = this.framesTable.selectedFrame;

      engine.executionCache.setCache( cacheKey, cacheData );
   }

   /**
    * GUI data initialization
    *
    */
   initialize()
   {
      let
      {
         N,
         activeFrames
      } = engine.subframeAnalyzer.sortFramesForLocalNormalizationReference( this.frameGroup );
      this.N = N;
      this.activeFrames = activeFrames.slice();
      this.numberOfFramesSpinBox.updateContent();
      this.enableAllFrames();
      this.updateBestFrames();
      if ( this.hasCache() )
      {
         this.restoreFromCache();
      }
      else
      {
         this.updateContent();
         this.selectFirstFrame();
      }
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-LNReferenceSelector.js - Released 2026-05-10T11:05:00Z
