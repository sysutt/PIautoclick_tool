// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ImagePreviewDialog.js - Released 2026-05-10T11:05:00Z
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
 * Modal dialog for previewing a single image file.
 * Provides zoom, pan, STF (auto-stretch), and reset functionality.
 *
 * @param {string} filePath - Path to the image file to preview
 * @param {string} title - Optional title for the dialog (defaults to filename)
 */
var WBPPImagePreviewDialog = class extends Dialog
{
   constructor( filePath, title )
   {
      super();

      this.filePath = filePath;
      this.windowTitle = title ?? File.extractNameAndExtension( filePath );

      // Image data
      this.imageWindow = null;
      this.originalBitmap = null; // Cached original (unstretched) bitmap
      this.stretchedBitmap = null; // Cached STF-stretched bitmap
      this.currentBitmap = null; // Currently displayed bitmap (points to original or stretched)
      this.stfApplied = true; // STF is applied by default
      this.currentSTF = null; // Cached STF parameters

      this.stfButton = new ToolButton( this );
      this.stfButton.icon = this.scaledResource( ":/toolbar/image-stf-auto.png" );
      this.stfButton.setScaledFixedSize( 24, 24 );
      this.stfButton.toolTip = "<p>Toggle AutoStretch.</p>";
      this.stfButton.onMousePress = function()
      {
         this.dialog.toggleSTF();
      };

      if ( !this.loadImage() )
         return;

      this.imageView = new ImageView( this, this.currentBitmap );
      this.imageView.appendTopControl( this.stfButton );

      this.closeButton = new PushButton( this );
      this.closeButton.text = "Close";
      this.closeButton.icon = this.scaledResource( ":/icons/close.png" );
      this.closeButton.onClick = () =>
      {
         this.ok();
      };

      // Buttons sizer
      this.buttonsSizer = new HorizontalSizer;
      this.buttonsSizer.addStretch();
      this.buttonsSizer.add( this.closeButton );

      // Main layout
      this.sizer = new VerticalSizer;
      this.sizer.margin = 8;
      this.sizer.spacing = 8;
      this.sizer.add( this.imageView, 100 );
      this.sizer.add( this.buttonsSizer );

      // Set initial size (80% of screen)
      let screenWidth = this.availableScreenRect.width;
      let scaleFactor = ( screenWidth >= 5120 ) ? 0.60 : ( screenWidth >= 3840 ) ? 0.70 : 0.80;
      this.resize( this.availableScreenRect.width * scaleFactor, this.availableScreenRect.height * scaleFactor );

      this.onClose = () =>
      {
         // Clean up
         if ( this.imageWindow )
         {
            this.imageWindow.forceClose();
            this.imageWindow = null;
         }
         this.imageView.reset();
         this.originalBitmap.clear();
         this.stretchedBitmap.clear();
         this.currentBitmap = null;
      };
   }

   // -------------------------------------------------------------------------
   // Image loading and STF
   // -------------------------------------------------------------------------

   /**
    * Loads the image from the file path and computes STF.
    * Both original and stretched bitmaps are cached for fast toggling.
    * @returns {boolean} True if successful
    */
   loadImage()
   {
      try
      {
         // Open the image file
         this.imageWindow = ImageWindow.open( this.filePath )[ 0 ];
         if ( !this.imageWindow )
         {
            console.criticalln( "<end><cbr>Failed to open image: <raw>" + this.filePath + "</raw>" );
            return false;
         }

         // Create bitmap from the original image
         this.originalBitmap = new Bitmap( this.imageWindow.mainView.image.width, this.imageWindow.mainView.image.height );
         this.originalBitmap.assign( this.imageWindow.mainView.image.render() );

         // Compute and cache STF parameters
         this.currentSTF = WBPPUtils.computeSTFAutoStretch( this.imageWindow.mainView );

         // Create stretched bitmap using cached STF
         this.stretchedBitmap = this.createStretchedBitmap();

         // Start with STF applied by default
         this.currentBitmap = this.stretchedBitmap;
         this.stfApplied = true;
         this.updateSTFButtonState();

         return true;
      }
      catch ( e )
      {
         console.criticalln( "<end><cbr>Error loading image: " + e.message );
         return false;
      }
   }

   /**
    * Creates the stretched bitmap using the cached STF parameters.
    * @returns {Bitmap} The stretched bitmap
    */
   createStretchedBitmap()
   {
      let image = new Image( this.imageWindow.mainView.image );
      image.applyDisplayFunction( this.currentSTF );
      let bmp = image.render();
      image.free();
      return bmp;
   }

   /**
    * Updates the STF button icon and tooltip based on current state.
    */
   updateSTFButtonState()
   {
      if ( this.stfApplied )
      {
         this.stfButton.icon = this.scaledResource( ":/toolbar/image-stf-auto.png" );
         this.stfButton.toolTip = "<p>STF AutoStretch applied - click to show the original image.</p>";
      }
      else
      {
         this.stfButton.icon = this.scaledResource( ":/toolbar/image-stf.png" );
         this.stfButton.toolTip = "<p>Original image shown - click to apply STF AutoStretch.</p>";
      }
   }

   /**
    * Shows the STF-stretched image (uses cached bitmap).
    */
   showSTF()
   {
      this.currentBitmap = this.stretchedBitmap;
      this.stfApplied = true;
      this.updateSTFButtonState();
      this.imageView.regenerate( this.currentBitmap );
   }

   /**
    * Shows the original image (uses cached bitmap).
    */
   showOriginal()
   {
      this.currentBitmap = this.originalBitmap;
      this.stfApplied = false;
      this.updateSTFButtonState();
      this.imageView.regenerate( this.currentBitmap );
   }

   /**
    * Toggles between STF and original image (no recomputation).
    */
   toggleSTF()
   {
      if ( this.stfApplied )
         this.showOriginal();
      else
         this.showSTF();
   }
};

// ----------------------------------------------------------------------------
// EOF BPP-ImagePreviewDialog.js - Released 2026-05-10T11:05:00Z
