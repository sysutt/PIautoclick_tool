// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-FrameSelection.js - Released 2026-05-10T11:05:00Z
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

#include "BPP-ImagePreviewDialog.js"

// ----------------------------------------------------------------------------

/**
 * Control for displaying the list of frame groups.
 * Allows selecting a group to view its frames.
 */
var WBPPGroupsTable = class extends Control
{
   constructor( parent )
   {
      super( parent );

   this.groupsTree = new TreeBox( this );
   this.groupsTree.alternateRowColor = true;
   this.groupsTree.headerVisible = true;
   this.groupsTree.numberOfColumns = 5;
   this.groupsTree.setHeaderText( 0, "Group" );
   this.groupsTree.setHeaderText( 1, "Frames" );
   this.groupsTree.setHeaderText( 2, "Rejected" );
   this.groupsTree.setHeaderText( 3, "Disabled" );
   this.groupsTree.setHeaderText( 4, "" ); // Empty column for flexible space
   this.groupsTree.setHeaderAlignment( 0, TextAlignment.Left | TextAlignment.VertCenter );
   this.groupsTree.setHeaderAlignment( 1, TextAlignment.Right | TextAlignment.VertCenter );
   this.groupsTree.setHeaderAlignment( 2, TextAlignment.Right | TextAlignment.VertCenter );
   this.groupsTree.setHeaderAlignment( 3, TextAlignment.Right | TextAlignment.VertCenter );

   // Flag to suppress selection callback during updates
   this.suppressSelectionCallback = false;

   this.groupsTree.onCurrentNodeUpdated = ( node ) =>
   {
      if ( this.suppressSelectionCallback )
         return;
      if ( node && this.onGroupSelected )
         this.onGroupSelected( node.__frameGroup__ );
   };

   // Sizers
   this.sizer = new VerticalSizer;
   this.sizer.add( this.groupsTree );

   // Data
   this.groups = [];
   this.selectedGroup = undefined;
   }

   /**
    * Sets the list of frame groups to display.
    *
    * @param {Array} groups - Array of FrameGroup objects
    */
   setGroups( groups )
   {
      this.groups = groups || [];
      this.updateContent();
   }

   /**
    * Updates the tree view with the current groups.
    * Preserves the current selection if possible.
    *
    * @param {boolean} preserveSelection - If true, try to preserve the current selection (default: true)
    */
   updateContent( preserveSelection )
   {
      if ( preserveSelection === undefined )
         preserveSelection = true;

      // Remember currently selected group before clearing
      let previouslySelectedGroup = null;
      if ( preserveSelection && this.groupsTree.currentNode )
         previouslySelectedGroup = this.groupsTree.currentNode.__frameGroup__;

      // Suppress callback during rebuild to avoid triggering onGroupSelected
      this.suppressSelectionCallback = true;

      this.groupsTree.clear();

      let nodeToSelect = null;

      for ( let i = 0; i < this.groups.length; i++ )
      {
         let group = this.groups[ i ];
         let node = new TreeBoxNode();
         node.__frameGroup__ = group;

         // Group column (short string without frame counts)
         node.setText( 0, group.toShortString( false, false ) );
         node.setAlignment( 0, TextAlignment.Left );

         // Frames count column
         let frameCount = group.fileItems ? group.fileItems.length : 0;
         node.setText( 1, frameCount.toString() );
         node.setAlignment( 1, TextAlignment.Right );

         // Rejected count column
         let rejectedCount = this.countRejectedFrames( group );
         node.setText( 2, rejectedCount.toString() );
         node.setAlignment( 2, TextAlignment.Right );
         if ( rejectedCount > 0 )
            node.setTextColor( 2, 0xFFE57373 ); // Red tint for rejected

         // Disabled count column
         let disabledCount = this.countDisabledFrames( group );
         node.setText( 3, disabledCount.toString() );
         node.setAlignment( 3, TextAlignment.Right );
         if ( disabledCount > 0 )
            node.setTextColor( 3, 0xFF888888 ); // Gray tint for disabled

         this.groupsTree.add( node );

         // Check if this is the previously selected group
         if ( previouslySelectedGroup && group === previouslySelectedGroup )
            nodeToSelect = node;

         // Remember first node as fallback
         if ( i === 0 && !nodeToSelect )
            nodeToSelect = node;
      }

      // Restore selection (or select first if no previous selection)
      if ( nodeToSelect )
         this.groupsTree.currentNode = nodeToSelect;

      // Re-enable callback
      this.suppressSelectionCallback = false;

      // Adjust all columns except the last empty one (for flexible space)
      for ( let j = 0; j < this.groupsTree.numberOfColumns - 1; j++ )
         this.groupsTree.adjustColumnWidthToContents( j );
   }

   /**
    * Counts rejected frames in a group.
    *
    * @param {Object} group - Frame group
    * @returns {number} Number of rejected frames
    */
   countRejectedFrames( group )
   {
      if ( !group )
         return 0;
      return group.rejectedFrameCount();
   }

   /**
    * Counts disabled frames in a group.
    *
    * @param {Object} group - Frame group
    * @returns {number} Number of disabled frames
    */
   countDisabledFrames( group )
   {
      if ( !group )
         return 0;
      return group.disabledFrameCount();
   }

   /**
    * Programmatically selects a group.
    *
    * @param {FrameGroup} group - The group to select
    */
   selectGroup( group )
   {
      for ( let i = 0; i < this.groupsTree.numberOfChildren; i++ )
      {
         let node = this.groupsTree.child( i );
         if ( node.__frameGroup__ === group )
         {
            this.groupsTree.currentNode = node;
            this.selectedGroup = group;
            break;
         }
      }
   }
}

// ----------------------------------------------------------------------------

/**
 * Control for displaying the list of frames within a selected group.
 * Shows frame details and measured metrics.
 */
var WBPPFramesTable = class extends Control
{
   constructor( parent )
   {
      super( parent );

   this.framesTree = new TreeBox( this );
   this.framesTree.alternateRowColor = true;
   this.framesTree.headerVisible = true;
   this.framesTree.numberOfColumns = 10;
   this.framesTree.setHeaderText( 0, "#" );
   this.framesTree.setHeaderText( 1, "Status" );
   this.framesTree.setHeaderText( 2, "File name" );
   this.framesTree.setHeaderText( 3, "FWHM" );
   this.framesTree.setHeaderText( 4, "Eccentricity" );
   this.framesTree.setHeaderText( 5, "PSFSW" );
   this.framesTree.setHeaderText( 6, "Median" );
   this.framesTree.setHeaderText( 7, "Stars" );
   this.framesTree.setHeaderText( 8, "Custom" );
   this.framesTree.setHeaderText( 9, "" ); // Empty column for flexible space
   this.framesTree.setHeaderAlignment( 0, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 1, TextAlignment.Center | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 2, TextAlignment.Left | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 3, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 4, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 5, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 6, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 7, TextAlignment.Right | TextAlignment.VertCenter );
   this.framesTree.setHeaderAlignment( 8, TextAlignment.Right | TextAlignment.VertCenter );

   // Store original header texts for sort indicator
   this.originalHeaderTexts = [ "#", "Status", "File name", "FWHM", "Eccentricity", "PSFSW", "Median", "Stars", "Custom", "" ];
   this.sortColumnIndex = -1;

   // Mapping from metric keys to column indices
   this.metricKeyToColumn = {
      'FWHM': 3,
      'eccentricity': 4,
      'PSFSignalWeight': 5,
      'median': 6,
      'numberOfStars': 7,
      'custom': 8
   };

   // Custom formula state
   this.customFormulaValid = false;

   // Flag to suppress selection callback during updates
   this.suppressSelectionCallback = false;

   this.framesTree.onCurrentNodeUpdated = ( node ) =>
   {
      if ( this.suppressSelectionCallback )
         return;
      if ( node )
      {
         // Update internal selection state when user clicks on a frame
         this.selectedFrame = node.__activeFrame__;
         this.selectedIndex = node.__index__;

         if ( this.onFrameSelected )
            this.onFrameSelected( node.__activeFrame__, node.__index__ );
      }
   };

   this.framesTree.onNodeDoubleClicked = ( node ) =>
   {
      if ( node && node.__activeFrame__ )
      {
         if ( this.onFrameDoubleClicked )
            this.onFrameDoubleClicked( node.__activeFrame__, node.__index__ );
      }
   };

   // Sizers
   this.sizer = new VerticalSizer;
   this.sizer.add( this.framesTree );

   // Data
   this.activeFrames = [];
   this.selectedFrame = undefined;
   this.selectedIndex = -1;

   // Colors for rejected and disabled status
   this.rejectedColor = 0xFFE57373; // Light red
   this.acceptedColor = 0xFF81C784; // Light green
   this.disabledColor = 0xFF888888; // Gray for disabled frames
   }

   /**
    * Sets the list of active frames to display.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects
    * @param {number} preserveIndex - If provided, try to preserve selection at this index
    */
   setFrames( activeFrames, preserveIndex )
   {
      this.activeFrames = activeFrames || [];
      this.updateContent( preserveIndex );
   }

   /**
    * Updates the tree view with the current frames.
    * Preserves the current selection if possible.
    *
    * @param {number} preserveIndex - If provided, try to select this index after update
    */
   updateContent( preserveIndex )
   {
      // Remember currently selected index before clearing
      let indexToSelect = -1;
      if ( preserveIndex !== undefined && preserveIndex >= 0 )
         indexToSelect = preserveIndex;
      else if ( this.framesTree.currentNode )
         indexToSelect = this.framesTree.currentNode.__index__;

      // Suppress callback during rebuild
      this.suppressSelectionCallback = true;

      this.framesTree.clear();

      for ( let i = 0; i < this.activeFrames.length; i++ )
      {
         let frame = this.activeFrames[ i ];
         let node = new TreeBoxNode();
         node.__activeFrame__ = frame;
         node.__index__ = i;

         let descriptor = frame.descriptor
            ||
            {};
         let isRejected = descriptor.rejected || false;
         let isDisabled = descriptor.disabled || false;

         // Index column
         node.setText( 0, ( i + 1 ).toString() );
         node.setAlignment( 0, TextAlignment.Right );

         // Status column - disabled takes precedence over rejected for display
         if ( isDisabled )
            node.setIcon( 1, this.dialog.scaledResource( ":/browser/delete.png" ) );
         else
            node.setIcon( 1, this.dialog.scaledResource( isRejected ? ":/icons/delete.png" : ":/icons/check.png" ) );
         node.setAlignment( 1, TextAlignment.Center );

         // File name column
         node.setText( 2, File.extractNameAndExtension( frame.current || "" ) );
         node.setAlignment( 2, TextAlignment.Left );
         node.setToolTip( 2, frame.current || "" );
         if ( isRejected && !isDisabled )
            node.setTextColor( 2, this.rejectedColor );

         // FWHM column
         node.setText( 3, descriptor.FWHM != null && !isNaN( descriptor.FWHM ) ? descriptor.FWHM.toFixed( FrameFilterMetricDefinitions[ 0 ].decimals ) : "-" );
         node.setAlignment( 3, TextAlignment.Right );

         // Eccentricity column
         node.setText( 4, descriptor.eccentricity != null && !isNaN( descriptor.eccentricity ) ? descriptor.eccentricity.toFixed( FrameFilterMetricDefinitions[ 1 ].decimals ) : "-" );
         node.setAlignment( 4, TextAlignment.Right );

         // PSFSW column (using pre-computed normalized value)
         let psfswValue = descriptor.PSFSignalWeightNormalized;
         node.setText( 5, psfswValue != null && !isNaN( psfswValue ) ? psfswValue.toFixed( FrameFilterMetricDefinitions[ 2 ].decimals ) : "-" );
         node.setAlignment( 5, TextAlignment.Right );

         // Median column
         node.setText( 6, descriptor.median != null && !isNaN( descriptor.median ) ? descriptor.median.toFixed( FrameFilterMetricDefinitions[ 3 ].decimals ) : "-" );
         node.setAlignment( 6, TextAlignment.Right );

         // Stars column
         node.setText( 7, descriptor.numberOfStars != null && !isNaN( descriptor.numberOfStars ) ? descriptor.numberOfStars.toFixed( FrameFilterMetricDefinitions[ 4 ].decimals ) : "-" );
         node.setAlignment( 7, TextAlignment.Right );

         // Custom formula column
         let customValue = "-";
         if ( this.customFormulaValid && descriptor.hasOwnProperty( 'custom' ) )
         {
            let cv = descriptor.custom;
            if ( cv !== null && cv !== undefined && !isNaN( cv ) )
               customValue = cv.toFixed( FrameFilterMetricDefinitions[ 5 ].decimals );
         }
         node.setText( 8, customValue );
         node.setAlignment( 8, TextAlignment.Right );

         // Apply disabled styling to all columns at once
         if ( isDisabled )
         {
            // Use italic font to make disabled state visible even when selected
            let disabledFont = this.framesTree.font;
            disabledFont.italic = true;
            for ( let col = 0; col < this.framesTree.numberOfColumns - 1; col++ )
            {
               node.setTextColor( col, this.disabledColor );
               node.setFont( col, disabledFont );
            }
         }

         this.framesTree.add( node );
      }

      // Adjust all columns except the last empty one (for flexible space)
      for ( let j = 0; j < this.framesTree.numberOfColumns - 1; j++ )
         this.framesTree.adjustColumnWidthToContents( j );

      // Restore selection if valid
      if ( indexToSelect >= 0 && indexToSelect < this.framesTree.numberOfChildren )
      {
         this.framesTree.currentNode = this.framesTree.child( indexToSelect );
         this.selectedIndex = indexToSelect;
         this.selectedFrame = this.activeFrames[ indexToSelect ];
      }

      // Re-enable callback
      this.suppressSelectionCallback = false;
   }

   /**
    * Programmatically selects a frame by index.
    *
    * @param {number} index - The index of the frame to select
    */
   selectFrameByIndex( index )
   {
      if ( index >= 0 && index < this.framesTree.numberOfChildren )
      {
         let node = this.framesTree.child( index );
         this.framesTree.currentNode = node;
         this.selectedFrame = node.__activeFrame__;
         this.selectedIndex = index;
      }
   }

   /**
    * Clears the frames table.
    */
   clear()
   {
      this.activeFrames = [];
      this.selectedFrame = undefined;
      this.selectedIndex = -1;
      this.customFormulaValid = false;
      this.framesTree.clear();
   }

   /**
    * Sets the sort indicator on a specific column.
    * Clears any previous sort indicator.
    *
    * @param {number} columnIndex - The column to show sort indicator on (-1 to clear)
    */
   setSortColumn( columnIndex )
   {
      // Restore all headers to original text
      for ( let i = 0; i < this.originalHeaderTexts.length; i++ )
         this.framesTree.setHeaderText( i, this.originalHeaderTexts[ i ] );

      this.sortColumnIndex = columnIndex;

      // Add arrow to sorted column
      if ( columnIndex >= 0 && columnIndex < this.originalHeaderTexts.length )
      {
         let text = this.originalHeaderTexts[ columnIndex ];
         this.framesTree.setHeaderText( columnIndex, text + " ▼" );
      }
   }

   /**
    * Sets the sort indicator based on a metric key.
    *
    * @param {string|null} metricKey - The metric key to show sort for (null to clear)
    */
   setSortByMetricKey( metricKey )
   {
      let columnIndex = -1;
      if ( metricKey && this.metricKeyToColumn.hasOwnProperty( metricKey ) )
         columnIndex = this.metricKeyToColumn[ metricKey ];
      this.setSortColumn( columnIndex );
   }

   /**
    * Resets the sort indicator.
    */
   resetSortIndicator()
   {
      this.setSortColumn( -1 );
   }

   /**
    * Sets whether the custom formula is valid.
    * When valid, the custom column shows computed values.
    * When invalid, the custom column shows "-".
    *
    * @param {boolean} isValid - True if custom formula is valid
    */
   setCustomFormulaValid( isValid )
   {
      if ( this.customFormulaValid !== isValid )
      {
         this.customFormulaValid = isValid;
         // Refresh display to update custom column
         this.updateContent();
      }
   }
}

// ----------------------------------------------------------------------------

/**
 * WebView-based control for displaying a single metric plot.
 * Uses HTML/SVG for rendering beautiful, scalable charts.
 * Shows rejected frames in a different color.
 * Supports click-to-select functionality.
 * Can show a placeholder message when custom formula is invalid.
 * Includes an interactive sort button in the top-right corner.
 */
var WBPPMetricPlot = class extends Frame
{
   constructor( parent )
   {
      super( parent );

   // Plot configuration
   this.metricName = "";
   this.metricData = []; // Array of {value, rejected}
   this.highlightedIndex = -1;
   this.thresholdValue = null;
   this.thresholdMode = null;

   // Sort button state
   this.sortActive = false; // True if frames are sorted by this metric
   this.plotIndex = -1; // Index of this plot in the grid (set by parent)

   // Custom formula mode (for the dedicated custom formula plot - bottom right)
   this.isCustomFormulaPlot = false; // True if this is the dedicated custom formula plot
   this.placeholderMessage = null; // Message to show when formula is invalid

   // Chart layout constants (must match SVG generation)
   this.chartLayout = {
      svgWidth: 400,
      svgHeight: 200,
      marginLeft: 55,
      marginRight: 15,
      marginTop: 35,
      marginBottom: 25,
      titleHeight: 28 // Height of title area (must fit buttons)
   };

   // Button dimensions (positioned in title area, top-right corner)
   this.buttonLayout = {
      width: 27,
      height: 24,
      gap: 8, // Gap between buttons
      rightMargin: 4, // Distance from right edge
      topMargin: 2 // Distance from top
   };

   // Ensure no frame border affects coordinate calculations
   this.frameStyle = FrameStyle.Flat;

   // Color scheme (dark theme)
   this.colors = {
      background: "#1e1e2e",
      plotArea: "#252536",
      bar: "#2d6cb5",
      barRejected: "#e57373",
      highlight: "#f9a825",
      highlightRejected: "#ff8a65",
      grid: "#3a3a4a",
      text: "#cdd6f4",
      textMuted: "#6c7086",
      axis: "#585b70",
      threshold: "#f9a825",
      rejectionZone: "#1a0505"
   };

   // Store reference to self for event handlers
   let self = this;

   // WebView for rendering HTML content
   this.webView = new WebView( this );

   // Click overlay for capturing mouse events - sits on top of WebView
   // On Windows/Linux, transparent controls may not receive mouse events,
   // so we draw a nearly-invisible background to ensure event capture.
   this.clickOverlay = new Control( this );
   this.clickOverlay.cursor = new Cursor( StdCursor.PointingHand );

   // Draw a nearly-transparent background to ensure mouse events are captured
   // on all platforms (Windows/Linux require non-transparent areas for events)
   this.clickOverlay.onPaint = function()
   {
      let g = new Graphics( this );
      g.fillRect( this.boundsRect, new Brush( 0x01000000 ) ); // 1/255 alpha black
      g.end();
   };

   // Mouse click handler for clickOverlay
   this.clickOverlay.onMousePress = function( x, y, button, buttonState, modifiers )
   {
      if ( button !== MouseButton.Left )
         return;

      // Check if sort button was clicked
      if ( self.isSortButtonAtPosition( x, y ) )
      {
         if ( self.onSortButtonClicked )
            self.onSortButtonClicked( self.plotIndex );
         return;
      }

      let clickedIndex = self.getBarIndexAtPosition( x, y );
      if ( clickedIndex >= 0 && self.onBarClicked )
         self.onBarClicked( clickedIndex );
   };

   // Mouse move handler for cursor feedback
   this.clickOverlay.onMouseMove = function( x, y, buttonState, modifiers )
   {
      // Show pointer cursor for interactive elements
      if ( self.isSortButtonAtPosition( x, y ) )
         self.clickOverlay.cursor = new Cursor( StdCursor.PointingHand );
      else if ( self.getBarIndexAtPosition( x, y ) >= 0 )
         self.clickOverlay.cursor = new Cursor( StdCursor.PointingHand );
      else
         self.clickOverlay.cursor = new Cursor( StdCursor.Arrow );
   };

   // Layout: just the webview
   this.sizer = new VerticalSizer;
   this.sizer.add( this.webView, 100 );

   // Position the overlay on top of the WebView
   this.updateOverlaySize = function()
   {
      // Make overlay cover the entire control
      self.clickOverlay.setFixedSize( self.width, self.height );
      self.clickOverlay.move( 0, 0 );
      // Force repaint to ensure the nearly-transparent background is drawn
      self.clickOverlay.repaint();
   };

   this.onResize = function()
   {
      self.updateOverlaySize();
   };

   this.onShow = function()
   {
      self.updateOverlaySize();
   };

   // Initialize with empty chart
   this.updateChart();
   }

   /**
    * Calculates which bar index is at the given mouse position.
    *
    * @param {number} mouseX - Mouse X coordinate relative to control
    * @param {number} mouseY - Mouse Y coordinate relative to control
    * @returns {number} Bar index or -1 if no bar at position
    */
   getBarIndexAtPosition( mouseX, mouseY )
   {
      if ( this.metricData.length === 0 )
         return -1;

      // If showing custom formula placeholder (invalid formula), don't allow bar clicks
      if ( this.isCustomFormulaPlot && this.placeholderMessage )
         return -1;

      // Get control dimensions
      let controlWidth = this.width;
      let controlHeight = this.height;

      if ( controlWidth <= 0 || controlHeight <= 0 )
         return -1;

      // Calculate the chart area within the control
      // The WebView renders the SVG which fills the middle section
      let layout = this.chartLayout;

      // Title row is at the top, chart container fills the rest
      let chartAreaTop = layout.titleHeight;
      let chartAreaHeight = controlHeight - layout.titleHeight;

      // Check if Y is within chart area (below title row)
      if ( mouseY < chartAreaTop || mouseY > controlHeight )
         return -1;

      // Map mouse position to SVG viewBox coordinates
      // Account for chart container padding (0 5px 5px 5px in CSS)
      let chartPadX = 5; // Horizontal padding from .chart-container CSS
      let chartPadBottom = 5; // Bottom padding from .chart-container CSS
      let chartContentWidth = controlWidth - 2 * chartPadX;
      let chartContentHeight = chartAreaHeight - chartPadBottom;

      // X must account for horizontal padding offset
      let relX = ( ( mouseX - chartPadX ) / chartContentWidth ) * layout.svgWidth;
      // Y needs to account for title row offset, chart container scaling, and bottom padding
      let relY = ( ( mouseY - chartAreaTop ) / chartContentHeight ) * layout.svgHeight;

      // Check if within plot area (between the axes)
      let plotLeft = layout.marginLeft;
      let plotRight = layout.svgWidth - layout.marginRight;
      let plotTop = layout.marginTop;
      let plotBottom = layout.svgHeight - layout.marginBottom;

      if ( relX < plotLeft || relX > plotRight )
         return -1;
      if ( relY < plotTop || relY > plotBottom )
         return -1;

      // Calculate which bar was clicked
      let plotWidth = plotRight - plotLeft;
      let barSpacing = plotWidth / this.metricData.length;
      let barIndex = Math.floor( ( relX - plotLeft ) / barSpacing );

      // Validate index
      if ( barIndex >= 0 && barIndex < this.metricData.length )
      {
         // Check if this bar has valid data and is not disabled
         let item = this.metricData[ barIndex ];
         if ( item && !item.disabled && item.value !== null && item.value !== undefined && !isNaN( item.value ) )
            return barIndex;
      }

      return -1;
   }

   /**
    * Checks if the given position is over the sort button.
    * The sort button is the rightmost button in the title area.
    *
    * @param {number} mouseX - Mouse X coordinate relative to control
    * @param {number} mouseY - Mouse Y coordinate relative to control
    * @returns {boolean} True if position is over the sort button
    */
   isSortButtonAtPosition( mouseX, mouseY )
   {
      if ( this.metricData.length === 0 )
         return false;

      let controlWidth = this.width;
      let controlHeight = this.height;

      if ( controlWidth <= 0 || controlHeight <= 0 )
         return false;

      let btn = this.buttonLayout;

      // The WebView viewport is sized to the control's logical dimensions.
      // CSS pixels in the HTML map 1:1 to the control's logical pixels
      // (the WebView handles DPR internally for rendering).
      // Mouse coordinates from the overlay are already in logical pixels,
      // so we compare directly to the CSS pixel button positions.

      // Button position: anchored to top-right of the control
      let btnX = controlWidth - btn.rightMargin - btn.width;
      let btnY = btn.topMargin;

      // Generous hit margin (8px) to make the small button easier to click
      let hitMargin = 8;

      return mouseX >= btnX - hitMargin && mouseX <= btnX + btn.width + hitMargin
          && mouseY >= btnY - hitMargin && mouseY <= btnY + btn.height + hitMargin;
   }

   /**
    * Generates the HTML content for a placeholder message.
    *
    * @returns {string} Complete HTML document for the placeholder
    */
   generatePlaceholderHTML()
   {
      let name = this.metricName;
      let message = this.placeholderMessage || "No data";
      let colors = this.colors;
      let sortActive = this.sortActive;

      // Use orange color for custom formula title
      let titleColor = this.isCustomFormulaPlot ? colors.highlight : colors.text;
      let titleStyle = this.isCustomFormulaPlot
         ? 'text-shadow: 0 0 8px ' + colors.highlight + '40;'
         : '';

      // Button colors
      let sortBtnBorder = sortActive ? colors.highlight : colors.axis;
      let sortBtnIcon = sortActive ? colors.highlight : colors.textMuted;

      let html = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
         + '<style>'
         + '*, *::before, *::after { box-sizing: border-box; }'
         + 'html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; '
         + 'background: ' + colors.background + '; font-family: "Segoe UI", system-ui, sans-serif; }'
         + '.container { width: 100%; height: 100%; display: flex; flex-direction: column; }'
         + '.title-row { display: flex; align-items: center; justify-content: center; position: relative; '
         + 'padding: 0; height: 28px; width: 100%; box-sizing: border-box; }'
         + '.title { color: ' + titleColor + '; font-size: 13px; font-weight: 600; '
         + 'letter-spacing: 0.5px; ' + titleStyle + ' }'
         + '.buttons { position: absolute; right: 4px; top: 2px; display: flex; gap: 8px; }'
         + '.btn { width: 27px; height: 24px; border-radius: 4px; background: rgba(30, 30, 46, 0.8); '
         + 'display: flex; align-items: center; justify-content: center; padding: 0; cursor: pointer; box-sizing: border-box; }'
         + '.sort-btn { border: 2px solid ' + sortBtnBorder + '; }'
         + '.sort-icon { display: flex; align-items: center; gap: 2px; }'
         + '.sort-lines { display: flex; flex-direction: column; gap: 2px; }'
         + '.sort-line { height: 2px; background: ' + sortBtnIcon + '; border-radius: 1px; }'
         + '.sort-line-1 { width: 9px; }'
         + '.sort-line-2 { width: 6px; }'
         + '.sort-line-3 { width: 3px; }'
         + '.sort-arrow { font-size: 10px; color: ' + sortBtnIcon + '; line-height: 1; }'
         + '.message-container { flex: 1; display: flex; align-items: center; justify-content: center; '
         + 'background: ' + colors.plotArea + '; margin: 5px 10px; border-radius: 6px; }'
         + '.message { color: ' + colors.textMuted + '; font-size: 12px; text-align: center; padding: 20px; }'
         + '.message-icon { font-size: 32px; margin-bottom: 10px; opacity: 0.5; }'
         + '</style></head><body>'
         + '<div class="container">'
         + '<div class="title-row">'
         + '<div class="title">' + name + '</div>'
         + '<div class="buttons">'
         + '<div class="btn sort-btn">'
         + '<div class="sort-icon">'
         + '<div class="sort-lines">'
         + '<div class="sort-line sort-line-1"></div>'
         + '<div class="sort-line sort-line-2"></div>'
         + '<div class="sort-line sort-line-3"></div>'
         + '</div>'
         + '<div class="sort-arrow">▼</div>'
         + '</div>'
         + '</div>'
         + '</div>'
         + '</div>'
         + '<div class="message-container">'
         + '<div class="message">'
         + '<div class="message-icon">⚠</div>'
         + '<div>' + message + '</div>'
         + '</div>'
         + '</div>'
         + '</div></body></html>';

      return html;
   }

   /**
    * Generates the HTML content for the plot.
    *
    * @returns {string} Complete HTML document for the chart
    */
   generateHTML()
   {
      // If we have a placeholder message, show that instead
      if ( this.placeholderMessage )
         return this.generatePlaceholderHTML();

      let data = this.metricData;
      let name = this.metricName;
      let highlightIdx = this.highlightedIndex;
      let colors = this.colors;
      let threshold = this.thresholdValue;
      let thresholdMode = this.thresholdMode;

      // Filter valid data points and track indices (exclude disabled frames)
      let validData = [];
      for ( let i = 0; i < data.length; i++ )
      {
         let item = data[ i ];
         // Skip disabled frames entirely - they don't appear in the plot
         if ( item && item.disabled )
            continue;
         if ( item && item.value !== null && item.value !== undefined && !isNaN( item.value ) )
            validData.push(
            {
               index: i,
               value: item.value,
               rejected: item.rejected || false,
               disabled: false
            } );
      }

      // Calculate statistics (only accepted non-disabled frames)
      let minVal = Infinity,
         maxVal = -Infinity,
         sum = 0,
         acceptedCount = 0;
      for ( let i = 0; i < validData.length; i++ )
      {
         let v = validData[ i ].value;
         if ( v < minVal ) minVal = v;
         if ( v > maxVal ) maxVal = v;
         if ( !validData[ i ].rejected )
         {
            sum += v;
            acceptedCount++;
         }
      }
      let avgVal = acceptedCount > 0 ? sum / acceptedCount : 0;

      // Add padding to range
      let range = maxVal - minVal;
      if ( range === 0 ) range = maxVal * 0.1 || 1;
      let padding = range * 0.1;
      let yMin = minVal - padding;
      let yMax = maxVal + padding;
      if ( yMin < 0 && minVal >= 0 ) yMin = 0;

      // Include threshold in range if set
      if ( threshold !== null && !isNaN( threshold ) )
      {
         if ( threshold < yMin ) yMin = threshold - padding;
         if ( threshold > yMax ) yMax = threshold + padding;
      }

      // Format number for display
      let formatNum = ( n ) =>
      {
         if ( Math.abs( n ) >= 1000 ) return n.toFixed( 0 );
         if ( Math.abs( n ) >= 100 ) return n.toFixed( 1 );
         if ( Math.abs( n ) >= 10 ) return n.toFixed( 2 );
         if ( Math.abs( n ) >= 1 ) return n.toFixed( 3 );
         return n.toFixed( 4 );
      };

      // SVG dimensions
      let svgWidth = 400;
      let svgHeight = 200;
      let marginLeft = 55;
      let marginRight = 15;
      let marginTop = 35;
      let marginBottom = 25;
      let plotWidth = svgWidth - marginLeft - marginRight;
      let plotHeight = svgHeight - marginTop - marginBottom;

      // Generate SVG bars
      let bars = "";
      let barWidth = data.length > 0 ? Math.max( 2, ( plotWidth / data.length ) - 1 ) : 0;
      let barSpacing = data.length > 0 ? plotWidth / data.length : 0;

      for ( let i = 0; i < data.length; i++ )
      {
         let item = data[ i ];
         // Skip disabled frames - they don't appear in the plot
         if ( item && item.disabled )
            continue;
         if ( !item || item.value === null || item.value === undefined || isNaN( item.value ) )
            continue;

         let v = item.value;
         let isRejected = item.rejected || false;
         let x = marginLeft + i * barSpacing + ( barSpacing - barWidth ) / 2;
         let barHeight = ( ( v - yMin ) / ( yMax - yMin ) ) * plotHeight;
         let y = marginTop + plotHeight - barHeight;

         let isHighlighted = ( i === highlightIdx );
         let barColor;
         if ( isHighlighted )
            barColor = isRejected ? colors.highlightRejected : colors.highlight;
         else
            barColor = isRejected ? colors.barRejected : colors.bar;

         bars += '<rect x="' + x.toFixed( 1 ) + '" y="' + y.toFixed( 1 ) + '" '
            + 'width="' + barWidth.toFixed( 1 ) + '" height="' + barHeight.toFixed( 1 ) + '" '
            + 'fill="' + barColor + '" rx="3" opacity="' + ( isRejected ? '0.6' : '1' ) + '" filter="url(#barShadow)"/>';

         // Add marker for highlighted bar
         if ( isHighlighted )
         {
            bars += '<circle cx="' + ( x + barWidth / 2 ).toFixed( 1 ) + '" cy="' + ( y - 5 ).toFixed( 1 ) + '" '
               + 'r="3" fill="' + barColor + '"/>';
         }
      }

      // Generate Y-axis ticks
      let yTicks = "";
      let numTicks = 5;
      for ( let i = 0; i <= numTicks; i++ )
      {
         let tickVal = yMin + ( yMax - yMin ) * ( i / numTicks );
         let tickY = marginTop + plotHeight - ( plotHeight * i / numTicks );
         yTicks += '<line x1="' + ( marginLeft - 5 ) + '" y1="' + tickY.toFixed( 1 ) + '" '
            + 'x2="' + marginLeft + '" y2="' + tickY.toFixed( 1 ) + '" stroke="' + colors.axis + '" stroke-width="1"/>';
         yTicks += '<text x="' + ( marginLeft - 8 ) + '" y="' + ( tickY + 3 ).toFixed( 1 ) + '" '
            + 'fill="' + colors.textMuted + '" font-size="9" text-anchor="end">' + formatNum( tickVal ) + '</text>';
         // Grid line
         yTicks += '<line x1="' + marginLeft + '" y1="' + tickY.toFixed( 1 ) + '" '
            + 'x2="' + ( svgWidth - marginRight ) + '" y2="' + tickY.toFixed( 1 ) + '" '
            + 'stroke="' + colors.grid + '" stroke-width="0.5" stroke-dasharray="3,3"/>';
      }

      // Threshold line and rejection zone
      let thresholdLine = "";
      let rejectionZone = "";
      if ( threshold !== null && !isNaN( threshold ) )
      {
         let threshY = marginTop + plotHeight - ( ( threshold - yMin ) / ( yMax - yMin ) ) * plotHeight;
         // Clamp threshY to plot bounds
         threshY = Math.max( marginTop, Math.min( marginTop + plotHeight, threshY ) );

         // Rejection zone: colored area showing which values would be rejected
         // LESS_THAN mode: values >= threshold are rejected (zone above line)
         // GREATER_THAN mode: values <= threshold are rejected (zone below line)
         let zoneY, zoneHeight;
         if ( thresholdMode === FrameFilterCompareMode.LESS_THAN )
         {
            // Rejection zone is ABOVE the threshold (higher values rejected)
            zoneY = marginTop;
            zoneHeight = threshY - marginTop;
         }
         else
         {
            // Rejection zone is BELOW the threshold (lower values rejected)
            zoneY = threshY;
            zoneHeight = marginTop + plotHeight - threshY;
         }

         if ( zoneHeight > 0 )
         {
            rejectionZone = '<rect x="' + marginLeft + '" y="' + zoneY.toFixed( 1 ) + '" '
               + 'width="' + plotWidth + '" height="' + zoneHeight.toFixed( 1 ) + '" '
               + 'fill="' + colors.rejectionZone + '" opacity="0.55" rx="2"/>';
         }

         // Threshold line
         thresholdLine = '<line x1="' + marginLeft + '" y1="' + threshY.toFixed( 1 ) + '" '
            + 'x2="' + ( svgWidth - marginRight ) + '" y2="' + threshY.toFixed( 1 ) + '" '
            + 'stroke="' + colors.threshold + '" stroke-width="2" stroke-dasharray="8,4"/>';
         // Threshold label
         let labelText = ( thresholdMode === FrameFilterCompareMode.LESS_THAN ? "<" : ">" ) + " " + formatNum( threshold );
         thresholdLine += '<text x="' + ( svgWidth - marginRight - 5 ) + '" y="' + ( threshY - 5 ).toFixed( 1 ) + '" '
            + 'fill="' + colors.threshold + '" font-size="10" text-anchor="end" font-weight="bold">' + labelText + '</text>';
      }

      // Average line (only for accepted)
      let avgLine = "";
      if ( acceptedCount > 0 )
      {
         let avgY = marginTop + plotHeight - ( ( avgVal - yMin ) / ( yMax - yMin ) ) * plotHeight;
         avgLine = '<line x1="' + marginLeft + '" y1="' + avgY.toFixed( 1 ) + '" '
            + 'x2="' + ( svgWidth - marginRight ) + '" y2="' + avgY.toFixed( 1 ) + '" '
            + 'stroke="#a6e3a1" stroke-width="1.5" stroke-dasharray="5,3"/>';
         // Average value label on the left side
         avgLine += '<text x="' + ( marginLeft + 5 ) + '" y="' + ( avgY - 4 ).toFixed( 1 ) + '" '
            + 'fill="#a6e3a1" font-size="9" text-anchor="start" font-weight="bold">' + formatNum( avgVal ) + '</text>';
      }

      // Use orange color for custom formula title to make it prominent
      let isCustom = this.isCustomFormulaPlot;
      let titleColor = isCustom ? colors.highlight : colors.text;
      let titleStyle = isCustom
         ? 'text-shadow: 0 0 8px ' + colors.highlight + '40;'
         : '';

      // Button states
      let sortActive = this.sortActive;

      // Button colors based on state
      let sortBtnBorder = sortActive ? colors.highlight : colors.axis;
      let sortBtnIcon = sortActive ? colors.highlight : colors.textMuted;

      // Build complete HTML
      let html = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
         + '<style>'
         + '*, *::before, *::after { box-sizing: border-box; }'
         + 'html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; '
         + 'background: ' + colors.background + '; font-family: "Segoe UI", system-ui, sans-serif; }'
         + '.container { width: 100%; height: 100%; display: flex; flex-direction: column; }'
         + '.title-row { display: flex; align-items: center; justify-content: center; position: relative; '
         + 'padding: 0; height: 28px; width: 100%; box-sizing: border-box; }'
         + '.title { color: ' + titleColor + '; font-size: 13px; font-weight: 600; '
         + 'letter-spacing: 0.5px; ' + titleStyle + ' }'
         + '.buttons { position: absolute; right: 4px; top: 2px; display: flex; gap: 8px; }'
         + '.btn { width: 27px; height: 24px; border-radius: 4px; background: rgba(30, 30, 46, 0.8); '
         + 'display: flex; align-items: center; justify-content: center; padding: 0; cursor: pointer; box-sizing: border-box; }'
         + '.sort-btn { border: 2px solid ' + sortBtnBorder + '; }'
         + '.sort-icon { display: flex; align-items: center; gap: 2px; }'
         + '.sort-lines { display: flex; flex-direction: column; gap: 2px; }'
         + '.sort-line { height: 2px; background: ' + sortBtnIcon + '; border-radius: 1px; }'
         + '.sort-line-1 { width: 9px; }'
         + '.sort-line-2 { width: 6px; }'
         + '.sort-line-3 { width: 3px; }'
         + '.sort-arrow { font-size: 10px; color: ' + sortBtnIcon + '; line-height: 1; }'
         + '.chart-container { flex: 1; display: flex; align-items: stretch; justify-content: stretch; padding: 0 5px 5px 5px; overflow: hidden; }'
         + 'svg { width: 100%; height: 100%; }'
         + '</style></head><body>'
         + '<div class="container">'
         + '<div class="title-row">'
         + '<div class="title">' + name + '</div>'
         + '<div class="buttons">'
         + '<div class="btn sort-btn">'
         + '<div class="sort-icon">'
         + '<div class="sort-lines">'
         + '<div class="sort-line sort-line-1"></div>'
         + '<div class="sort-line sort-line-2"></div>'
         + '<div class="sort-line sort-line-3"></div>'
         + '</div>'
         + '<div class="sort-arrow">▼</div>'
         + '</div>'
         + '</div>'
         + '</div>'
         + '</div>'
         + '<div class="chart-container">'
         + '<svg viewBox="0 0 ' + svgWidth + ' ' + svgHeight + '" preserveAspectRatio="none">'
         + '<defs><filter id="barShadow" x="-20%" y="-20%" width="140%" height="140%">'
         + '<feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.4"/>'
         + '</filter></defs>'
         + '<rect x="' + marginLeft + '" y="' + marginTop + '" width="' + plotWidth + '" height="' + plotHeight + '" '
         + 'fill="' + colors.plotArea + '" rx="3"/>'
         + yTicks + bars + rejectionZone + avgLine + thresholdLine
         + '<line x1="' + marginLeft + '" y1="' + marginTop + '" x2="' + marginLeft + '" y2="' + ( marginTop + plotHeight ) + '" '
         + 'stroke="' + colors.axis + '" stroke-width="1"/>'
         + '<line x1="' + marginLeft + '" y1="' + ( marginTop + plotHeight ) + '" x2="' + ( svgWidth - marginRight ) + '" '
         + 'y2="' + ( marginTop + plotHeight ) + '" stroke="' + colors.axis + '" stroke-width="1"/>'
         + '</svg></div>'
         + '</div></body></html>';

      return html;
   }

   /**
    * Updates the WebView with new chart content.
    */
   updateChart()
   {
      let html = this.generateHTML();
      this.webView.setHTML( html );
      // Ensure overlay is correctly sized after chart update
      this.updateOverlaySize();
   }

   /**
    * Sets the metric name and data for this plot.
    *
    * @param {string} name - The metric name (displayed as title)
    * @param {Array} data - Array of {value, rejected} objects
    */
   setMetricData( name, data )
   {
      this.metricName = name;
      this.metricData = data || [];
      this.updateChart();
   }

   /**
    * Sets the threshold line for the metric.
    *
    * @param {number} value - Threshold value
    * @param {number} mode - FrameFilterCompareMode
    */
   setThreshold( value, mode )
   {
      this.thresholdValue = value;
      this.thresholdMode = mode;
      this.updateChart();
   }

   /**
    * Highlights a specific data point (e.g., when a frame is selected).
    *
    * @param {number} index - The index of the data point to highlight
    */
   setHighlightedIndex( index )
   {
      this.highlightedIndex = index;
      this.updateChart();
   }

   /**
    * Sets whether this plot's metric is the active sort criterion.
    *
    * @param {boolean} active - True if sorting by this metric
    */
   setSortActive( active )
   {
      if ( this.sortActive !== active )
      {
         this.sortActive = active;
         this.updateChart();
      }
   }

   /**
    * Shows a placeholder message instead of the chart.
    *
    * @param {string} message - The message to display
    */
   showPlaceholder( message )
   {
      this.placeholderMessage = message;
      this.updateChart();
   }

   /**
    * Hides the placeholder and shows the chart.
    */
   hidePlaceholder()
   {
      this.placeholderMessage = null;
      this.updateChart();
   }

   /**
    * Marks this plot as the dedicated custom formula plot.
    * Sets up the title and visual styling for custom formula display.
    */
   setAsCustomFormulaPlot()
   {
      this.isCustomFormulaPlot = true;
      this.metricName = "★ Custom Formula";
   }

   /**
    * Clears the plot data.
    */
   clear()
   {
      this.metricData = [];
      this.highlightedIndex = -1;
      this.thresholdValue = null;
      this.thresholdMode = null;
      this.placeholderMessage = null;
      this.updateChart();
   }
}

// ----------------------------------------------------------------------------

/**
 * Grid container for multiple metric plots.
 * Arranges plots in 2 rows x 3 columns grid layout with fixed metrics:
 *   Row 1: FWHM, Eccentricity, PSF Signal Weight
 *   Row 2: Median, Stars, Custom Formula
 * The 6th plot (bottom-right) is always dedicated to Custom Formula.
 * Supports click-to-select on any plot.
 */
var WBPPMetricPlotsGrid = class extends Control
{
   constructor( parent )
   {
      super( parent );

   // Fixed plot layout: metrics for plots 0-4, plot 5 is custom formula
   // Order: FWHM, Eccentricity, PSFSignalWeight, Median, Stars (skipping SNR)
   this.plotMetrics = [
   {
      name: "FWHM",
      key: "FWHM"
   },
   {
      name: "Eccentricity",
      key: "eccentricity"
   },
   {
      name: "PSF Signal Weight",
      key: "PSFSignalWeight"
   },
   {
      name: "Median",
      key: "median"
   },
   {
      name: "Stars",
      key: "numberOfStars"
   } ];

   // Custom formula state
   this.customFormulaValid = false;
   this.customFormulaEnabled = false;
   this.activeFrames = []; // Store frames for refresh

   // Sort state: which plot (if any) is the active sort criterion
   this.activeSortPlotIndex = -1; // -1 means sorting by index (no plot active)

   // Store reference for closures
   let self = this;

   // Create 6 plot controls (2 rows x 3 columns)
   // Plots 0-4 are for specific metrics, plot 5 is custom formula
   this.plots = [];
   for ( let i = 0; i < 6; i++ )
   {
      let plot = new WBPPMetricPlot( this );
      plot.plotIndex = i; // Set plot index for event handling

      if ( i < 5 )
      {
         // Regular metric plot
         plot.setMetricData( this.plotMetrics[ i ].name, [] );
      }
      else
      {
         // Custom formula plot (index 5, bottom-right)
         plot.setAsCustomFormulaPlot();
         plot.showPlaceholder( "No custom formula defined or active" );
      }

      // Handle click events from any plot
      plot.onBarClicked = function( index )
      {
         if ( self.onFrameClicked )
            self.onFrameClicked( index );
      };

      // Handle sort button clicks
      plot.onSortButtonClicked = function( plotIndex )
      {
         self.handleSortButtonClick( plotIndex );
      };

      this.plots.push( plot );
   }

   // Layout: 2 rows x 3 columns
   // Row 1: FWHM, Eccentricity, PSF Signal Weight
   let row1 = new HorizontalSizer;
   row1.spacing = 8;
   row1.add( this.plots[ 0 ], 100 );
   row1.add( this.plots[ 1 ], 100 );
   row1.add( this.plots[ 2 ], 100 );

   // Row 2: Median, Stars, Custom Formula
   let row2 = new HorizontalSizer;
   row2.spacing = 8;
   row2.add( this.plots[ 3 ], 100 );
   row2.add( this.plots[ 4 ], 100 );
   row2.add( this.plots[ 5 ], 100 );

   this.sizer = new VerticalSizer;
   this.sizer.spacing = 8;
   this.sizer.add( row1, 100 );
   this.sizer.add( row2, 100 );
   }

   /**
    * Updates all plots with data from the provided active frames.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects with descriptors
    */
   setFrames( activeFrames )
   {
      // Store frames for refresh
      this.activeFrames = activeFrames || [];

      // Update plots 0-4 with their respective metrics
      for ( let i = 0; i < 5 && i < this.plots.length; i++ )
      {
         let plot = this.plots[ i ];
         let metricDef = this.plotMetrics[ i ];
         let data = [];

         for ( let j = 0; j < activeFrames.length; j++ )
         {
            let frame = activeFrames[ j ];
            let descriptor = frame.descriptor ||
            {};
            // Use pre-computed normalized value for PSFSignalWeight
            let value;
            if ( metricDef.key === 'PSFSignalWeight' )
               value = descriptor.PSFSignalWeightNormalized;
            else
               value = descriptor.hasOwnProperty( metricDef.key ) ? descriptor[ metricDef.key ] : null;
            data.push(
            {
               value: value !== undefined ? value : null,
               rejected: descriptor.rejected || false,
               disabled: descriptor.disabled || false
            } );
         }

         plot.setMetricData( metricDef.name, data );
      }

      // Update plot 5 (custom formula)
      this.updateCustomFormulaPlot( activeFrames );
   }

   /**
    * Updates the custom formula plot (plot index 5) with data.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects
    */
   updateCustomFormulaPlot( activeFrames )
   {
      let plot = this.plots[ 5 ];
      activeFrames = activeFrames || this.activeFrames;

      if ( !this.customFormulaValid || !this.customFormulaEnabled )
      {
         // Show placeholder for invalid/empty formula or disabled filter
         plot.showPlaceholder( "No custom formula defined or active" );
         return;
      }

      // Collect custom formula values
      let data = [];
      let hasValidData = false;

      for ( let j = 0; j < activeFrames.length; j++ )
      {
         let descriptor = activeFrames[ j ].descriptor ||
         {};
         let value = descriptor.hasOwnProperty( 'custom' ) ? descriptor.custom : null;
         if ( value !== null && value !== undefined && !isNaN( value ) )
            hasValidData = true;
         data.push(
         {
            value: value !== undefined ? value : null,
            rejected: descriptor.rejected || false,
            disabled: descriptor.disabled || false
         } );
      }

      if ( !hasValidData )
      {
         // No computed values yet
         plot.showPlaceholder( "Custom values not computed" );
         return;
      }

      // Show the data
      plot.hidePlaceholder();
      plot.setMetricData( "★ Custom Formula", data );
   }

   /**
    * Sets whether the custom formula is valid.
    * Updates the placeholder display accordingly.
    *
    * @param {boolean} isValid - True if formula is valid
    */
   setCustomFormulaValid( isValid )
   {
      this.customFormulaValid = isValid;
      this.updateCustomFormulaPlot( this.activeFrames );
   }

   /**
    * Sets whether the custom formula filter is enabled (checkbox checked).
    * Updates the placeholder display accordingly.
    *
    * @param {boolean} isEnabled - True if custom formula filter is enabled
    */
   setCustomFormulaEnabled( isEnabled )
   {
      this.customFormulaEnabled = isEnabled;
      this.updateCustomFormulaPlot( this.activeFrames );
   }

   /**
    * Updates threshold display on a specific plot.
    *
    * @param {number} index - Plot index
    * @param {number} value - Threshold value
    * @param {number} mode - FrameFilterCompareMode
    */
   setThreshold( index, value, mode )
   {
      if ( index >= 0 && index < this.plots.length )
         this.plots[ index ].setThreshold( value, mode );
   }

   /**
    * Highlights the specified frame index across all plots.
    *
    * @param {number} index - The frame index to highlight
    */
   setHighlightedIndex( index )
   {
      for ( let i = 0; i < this.plots.length; i++ )
         this.plots[ i ].setHighlightedIndex( index );
   }

   /**
    * Handles a sort button click on a plot.
    * Toggles the sort state: if already active, deactivates (sort by index).
    * If inactive, activates sorting by this plot's metric.
    *
    * @param {number} plotIndex - Index of the plot whose button was clicked
    */
   handleSortButtonClick( plotIndex )
   {
      // Toggle: if already active, deactivate (sort by index)
      if ( this.activeSortPlotIndex === plotIndex )
         this.setActiveSortPlot( -1 );
      else
         this.setActiveSortPlot( plotIndex );
   }

   /**
    * Sets the active sort plot and updates visual states.
    *
    * @param {number} plotIndex - Index of the plot to activate (-1 for index sorting)
    * @param {boolean} suppressCallback - If true, don't fire onSortPlotChanged (used for syncing)
    */
   setActiveSortPlot( plotIndex, suppressCallback )
   {
      this.activeSortPlotIndex = plotIndex;

      // Update all plots' visual state
      for ( let i = 0; i < this.plots.length; i++ )
         this.plots[ i ].setSortActive( i === plotIndex );

      // Notify parent of sort change (unless suppressed)
      if ( !suppressCallback && this.onSortPlotChanged )
         this.onSortPlotChanged( plotIndex );
   }

   /**
    * Gets the currently active sort plot index.
    *
    * @returns {number} Plot index or -1 if sorting by index
    */
   getActiveSortPlotIndex()
   {
      return this.activeSortPlotIndex;
   }

   /**
    * Gets the metric key for the active sort plot.
    *
    * @returns {string|null} Metric key or null for index sorting
    */
   getActiveSortMetricKey()
   {
      if ( this.activeSortPlotIndex < 0 )
         return null;

      // Plot 5 is the custom formula plot
      if ( this.activeSortPlotIndex === 5 )
         return 'custom';

      // Plots 0-4 use their respective metrics
      if ( this.activeSortPlotIndex < this.plotMetrics.length )
         return this.plotMetrics[ this.activeSortPlotIndex ].key;

      return null;
   }

   /**
    * Clears all plots.
    */
   clear()
   {
      this.activeFrames = [];
      this.activeSortPlotIndex = -1;
      this.customFormulaValid = false;
      this.customFormulaEnabled = false;
      for ( let i = 0; i < this.plots.length; i++ )
      {
         this.plots[ i ].clear();
         this.plots[ i ].setSortActive( false );
      }
      // Reset custom formula plot to show placeholder
      this.plots[ 5 ].showPlaceholder( "No custom formula defined or active" );
   }

   /**
    * Resets the sort state (deactivates all sort buttons).
    */
   resetSortState()
   {
      this.activeSortPlotIndex = -1;
      for ( let i = 0; i < this.plots.length; i++ )
         this.plots[ i ].setSortActive( false );
   }

   /**
    * Gets the list of metric names for plots 0-4 (excluding custom formula).
    *
    * @returns {Array} Array of {index, name, key} objects
    */
   getMetricNames()
   {
      let names = [];
      for ( let i = 0; i < this.plotMetrics.length; i++ )
         names.push(
         {
            index: i,
            name: this.plotMetrics[ i ].name,
            key: this.plotMetrics[ i ].key
         } );
      return names;
   }
}

// ----------------------------------------------------------------------------

/**
 * Filter panel containing all filter criteria including custom formula.
 * This is a bordered Frame wrapper around the shared WBPPFrameSelectionFiltersControl.
 * Contains ONLY the filters - buttons are added separately in the dialog.
 */
var WBPPFilterPanel = class extends Frame
{
   constructor( parent )
   {
      super( parent );

   // Set up bordered container
   this.lineWidth = 1;
   this.frameStyle = FrameStyle.Box;

   // Create the shared filter control (with title, WITHOUT apply-to-all button)
   this.innerControl = new WBPPFrameSelectionFiltersControl( this, true /* showTitle */ , false /* showApplyToAll */ );

   // Store reference for closures
   let self = this;

   // Proxy callbacks from inner control
   this.innerControl.onFilterChanged = () =>
   {
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };
   this.innerControl.onFormulaChanged = () =>
   {
      if ( this.onFormulaChanged )
         this.onFormulaChanged();
   };
   this.innerControl.onImportFromFrame = function( metricKey )
   {
      if ( self.onImportFromFrame )
         self.onImportFromFrame( metricKey );
   };

   // Expose filters array for compatibility
   this.filters = this.innerControl.filters;
   this.customFormulaFilter = this.innerControl.customFormulaFilter;

   // Layout - internal margin only
   this.sizer = new VerticalSizer;
   this.sizer.margin = 8;
   this.sizer.add( this.innerControl );

   }

   getCustomFormula() { return this.innerControl.getCustomFormula(); }
   isCustomFormulaValid() { return this.innerControl.isCustomFormulaValid(); }
   isCustomFormulaEnabled() { return this.innerControl.isCustomFormulaEnabled(); }
   applyCustomFormulaToGroup( group ) { return this.innerControl.applyCustomFormulaToGroup( group ); }
   getFilterConfigs() { return this.innerControl.getFilterConfigs(); }
   setFilterConfigs( configs ) { return this.innerControl.setFilterConfigs( configs ); }
   initializeFromFrames( activeFrames ) { return this.innerControl.initializeFromFrames( activeFrames ); }
   initializeCustomFromFrames( activeFrames ) { return this.innerControl.initializeCustomFromFrames( activeFrames ); }
   testFrame( descriptor ) { return this.innerControl.testFrame( descriptor ); }
   setImportButtonsVisible( show ) { return this.innerControl.setImportButtonsVisible( show ); }
   importValueForMetric( metricKey, value ) { return this.innerControl.importValueForMetric( metricKey, value ); }
   reset() { this.innerControl.reset(); }

   /**
    * Updates threshold visualization in plots grid.
    * Maps filter configs to the fixed plot layout:
    *   Plot 0: FWHM, Plot 1: Eccentricity, Plot 2: PSFSignalWeight
    *   Plot 3: Median, Plot 4: Stars, Plot 5: Custom Formula
    *
    * @param {WBPPMetricPlotsGrid} plotsGrid - Plots grid to update
    */
   updatePlotThresholds( plotsGrid )
   {
      // Map filter keys to plot indices (matching the fixed plot layout)
      let keyToPlotIndex = {
         'FWHM': 0,
         'eccentricity': 1,
         'PSFSignalWeight': 2,
         'median': 3,
         'numberOfStars': 4
      };

      // Update thresholds for plots 0-4 based on filter configs
      for ( let i = 0; i < this.filters.length; i++ )
      {
         let config = this.filters[ i ].getFilterConfig();

         // Skip custom formula - handled separately
         if ( config.isCustomFormula )
            continue;

         // Skip SNR - no longer has a plot
         if ( config.key === 'SNR' )
            continue;

         let plotIndex = keyToPlotIndex[ config.key ];
         if ( plotIndex !== undefined )
         {
            if ( config.enabled )
               plotsGrid.setThreshold( plotIndex, config.value, config.compareMode );
            else
               plotsGrid.setThreshold( plotIndex, null, null );
         }
      }

      // Update plot 5 (custom formula) threshold
      if ( this.customFormulaFilter )
      {
         let customConfig = this.customFormulaFilter.getFilterConfig();
         if ( customConfig && customConfig.enabled )
            plotsGrid.setThreshold( 5, customConfig.value, customConfig.compareMode );
         else
            plotsGrid.setThreshold( 5, null, null );
      }
   }
}

// ----------------------------------------------------------------------------

/**
 * Main dialog for frames selection and metric visualization.
 * Layout: Left side (Groups + Frames tables), Right side (Filter Panel), Bottom (Plots)
 *
 * @param {Array} groups - Array of FrameGroup objects to display
 */
var WBPPFrameSelectionDialog = class extends Dialog
{
   constructor( groups )
   {
      super();
   this.windowTitle = "Frame Selection";

   let spacing = 8;

   // -------------------------------------------------------------------------
   // SECTION 1: Frame Groups (left side, top)
   // -------------------------------------------------------------------------

   // Groups section label
   this.groupsLabel = new Label( this );
   this.groupsLabel.text = "Frame Groups";
   this.groupsLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;
   let font = this.groupsLabel.font;
   font.bold = true;
   this.groupsLabel.font = font;

   // Groups table
   this.groupsTable = new WBPPGroupsTable( this );
   this.groupsTable.onGroupSelected = ( group ) =>
   {
      this.onGroupSelected( group );
   };

   // -------------------------------------------------------------------------
   // SECTION 2: Frames in Selected Group (left side, middle)
   // -------------------------------------------------------------------------

   // Frames section label
   this.framesLabel = new Label( this );
   this.framesLabel.text = "Frames in Selected Group";
   this.framesLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;
   this.framesLabel.font = font;

   // Frames table
   this.framesTable = new WBPPFramesTable( this );
   this.framesTable.onFrameSelected = ( frame, index ) =>
   {
      this.onFrameSelected( frame, index );
   };
   this.framesTable.onFrameDoubleClicked = ( frame, index ) =>
   {
      this.showImagePreview( frame );
   };

   // -------------------------------------------------------------------------
   // SECTION 3: Filter Panel and Buttons (right side)
   // -------------------------------------------------------------------------

   this.filterPanel = new WBPPFilterPanel( this );

   // Show import buttons in interactive dialog
   this.filterPanel.setImportButtonsVisible( true );

   this.filterPanel.onFilterChanged = () =>
   {
      // Update custom formula valid and enabled state in plots grid and frames table
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );
      this.applyFiltersToCurrentGroup();
   };
   this.filterPanel.onFormulaChanged = () =>
   {
      this.applyCustomFormulaToCurrentGroup();
      // Update custom formula valid and enabled state in plots grid and frames table
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );
   };
   this.filterPanel.onImportFromFrame = ( metricKey ) =>
   {
      this.importMetricFromSelectedFrame( metricKey );
   };

   // Apply to All button (created in dialog, not in filterPanel)
   this.applyToAllButton = new PushButton( this );
   this.applyToAllButton.text = "Apply to All Groups";
   this.applyToAllButton.icon = this.scaledResource( ":/icons/copy.png" );
   this.applyToAllButton.toolTip = "<p>Apply the current filter configuration to all frame groups.</p>";
   this.applyToAllButton.onClick = () =>
   {
      this.applyFiltersToAllGroups();
   };

   // Disable/Enable frame button
   this.disableFrameButton = new PushButton( this );
   this.disableFrameButton.text = "Disable Frame";
   this.disableFrameButton.icon = this.scaledResource( ":/browser/delete.png" );
   this.disableFrameButton.toolTip = "<p>Disable the selected frame. Disabled frames are excluded from "
      + "metric plots and statistics, and will be treated as rejected when the dialog is closed.</p>"
      + "<p>Use this to manually exclude outlier frames from analysis.</p>";
   this.disableFrameButton.enabled = false; // Disabled until a frame is selected
   this.disableFrameButton.onClick = () =>
   {
      this.toggleFrameDisabledState();
   };

   // Reset button - re-enables all disabled frames in current group
   this.resetDisabledButton = new PushButton( this );
   this.resetDisabledButton.text = "Reset Disabled";
   this.resetDisabledButton.icon = this.scaledResource( ":/icons/undo.png" );
   this.resetDisabledButton.toolTip = "<p>Re-enable all disabled frames in the current group.</p>";
   this.resetDisabledButton.onClick = () =>
   {
      this.resetDisabledFrames();
   };

   // -------------------------------------------------------------------------
   // LAYOUT: Top section with tables and filter panel
   // -------------------------------------------------------------------------

   // Left side: groupsTable, framesLabel, framesTable
   let leftSizer = new VerticalSizer;
   leftSizer.spacing = spacing;
   leftSizer.add( this.groupsTable, 30 );
   leftSizer.addSpacing( spacing );
   leftSizer.add( this.framesLabel );
   leftSizer.add( this.framesTable, 70 );

   // Right side: filterPanel, applyToAllButton, stretch, disableFrameButton, resetDisabledButton
   // No vertical padding so it aligns with tables
   let rightSizer = new VerticalSizer;
   rightSizer.spacing = spacing;
   rightSizer.add( this.filterPanel );
   rightSizer.addSpacing( spacing );
   rightSizer.add( this.applyToAllButton );
   rightSizer.addStretch();
   rightSizer.add( this.disableFrameButton );
   rightSizer.add( this.resetDisabledButton );

   // Horizontal sizer with left and right
   let tablesPanelSizer = new HorizontalSizer;
   tablesPanelSizer.spacing = spacing;
   tablesPanelSizer.add( leftSizer, 70 );
   tablesPanelSizer.add( rightSizer, 30 );

   // Top section: groupsLabel (full width) + tables/panel sizer
   let topSizer = new VerticalSizer;
   topSizer.spacing = spacing;
   topSizer.add( this.groupsLabel );
   topSizer.add( tablesPanelSizer, 100 );

   // -------------------------------------------------------------------------
   // SECTION 4: Metric Plots (2 rows x 3 columns)
   // -------------------------------------------------------------------------

   // Plots section label
   this.plotsLabel = new Label( this );
   this.plotsLabel.text = "Frame Metrics";
   this.plotsLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;
   this.plotsLabel.font = font;

   // Metric plots grid (2 rows x 3 columns)
   this.plotsGrid = new WBPPMetricPlotsGrid( this );

   // Handle clicks on plot bars to select frames
   this.plotsGrid.onFrameClicked = ( index ) =>
   {
      this.framesTable.selectFrameByIndex( index );
      // Explicitly update dialog state since programmatic selection doesn't trigger callback
      this.selectedFrame = this.framesTable.selectedFrame;
      this.plotsGrid.setHighlightedIndex( index );
      this.disableFrameButton.enabled = ( this.selectedFrame !== undefined );
      this.updateDisableButtonText();
   };

   // Handle sort button clicks on plots
   this.plotsGrid.onSortPlotChanged = ( plotIndex ) =>
   {
      // Update sort indicator in frames table
      let metricKey = this.plotsGrid.getActiveSortMetricKey();
      this.framesTable.setSortByMetricKey( metricKey );
      this.updateDisplayWithCurrentSort();
   };

   // -------------------------------------------------------------------------
   // SECTION 5: Dialog buttons
   // -------------------------------------------------------------------------

   this.resetButton = new PushButton( this );
   this.resetButton.text = "Reset";
   this.resetButton.icon = this.scaledResource( ":/icons/reload.png" );
   this.resetButton.toolTip = "<p>Reset all filter settings and rejection states.</p>";
   this.resetButton.onClick = () =>
   {
      this.reset();
   };

   this.cancelButton = new PushButton( this );
   this.cancelButton.text = "Cancel";
   this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
   this.cancelButton.toolTip = "<p>Cancel without applying rejections.</p>";
   this.cancelButton.onClick = () =>
   {
      this.cancel();
   };

   this.okButton = new PushButton( this );
   this.okButton.text = "OK";
   this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
   this.okButton.toolTip = "<p>Apply rejections and close.</p>";
   this.okButton.onClick = () =>
   {
      // Save current group's filter config before closing
      this.saveCurrentGroupFilterConfig();

      // Mark all disabled frames as rejected before closing
      // This ensures disabled frames are treated the same as rejected frames
      this.markDisabledFramesAsRejected();

      this.ok();
   };

   let buttonsSizer = new HorizontalSizer;
   buttonsSizer.addStretch();
   buttonsSizer.add( this.resetButton );
   buttonsSizer.addSpacing( spacing );
   buttonsSizer.add( this.cancelButton );
   buttonsSizer.addSpacing( spacing );
   buttonsSizer.add( this.okButton );

   // -------------------------------------------------------------------------
   // MAIN LAYOUT
   // -------------------------------------------------------------------------

   this.sizer = new VerticalSizer;
   this.sizer.margin = spacing;
   this.sizer.spacing = spacing;
   this.sizer.add( topSizer, 45 );
   this.sizer.addSpacing( spacing );
   this.sizer.add( this.plotsLabel );
   this.sizer.add( this.plotsGrid, 55 );
   this.sizer.addSpacing( spacing );
   this.sizer.add( buttonsSizer );

   // Ensure layout is calculated before setting size
   this.ensureLayoutUpdated();
   this.initialSizeAndPos();

   // -------------------------------------------------------------------------
   // DATA MANAGEMENT
   // -------------------------------------------------------------------------

   this.groups = groups || [];
   this.selectedGroup = undefined;
   this.selectedFrame = undefined;

   this.initialize();
   }

   // Window size and position
   initialSizeAndPos()
   {
      // Scale factor based on screen resolution
      // 4K: 3840x2160, 5K: 5120x2880
      let screenWidth = this.availableScreenRect.width;
      let scaleFactor;

      if ( screenWidth >= 5120 )
         scaleFactor = 0.80;
      else if ( screenWidth >= 3840 )
         scaleFactor = 0.85;
      else
         scaleFactor = 0.9;

      this.width = this.availableScreenRect.width * scaleFactor;
      this.height = this.availableScreenRect.height * scaleFactor;

      // Limit aspect ratio to 21:9 (ultrawide)
      const maxAspectRatio = 21 / 9;
      if ( this.width / this.height > maxAspectRatio )
         this.width = this.height * maxAspectRatio;

      let origin = new Point(
         ( this.availableScreenRect.width - this.width ) / 2,
         ( this.availableScreenRect.height - this.height ) / 2 );
      this.move( origin );
   }

   /**
    * Marks all disabled frames as rejected across all groups.
    * Called when OK button is clicked to ensure disabled frames
    * are treated the same as rejected frames in downstream processing.
    */
   markDisabledFramesAsRejected()
   {
      for ( let i = 0; i < this.groups.length; i++ )
      {
         let group = this.groups[ i ];
         let frames = group.activeFrames();
         for ( let j = 0; j < frames.length; j++ )
         {
            let descriptor = frames[ j ].descriptor;
            if ( descriptor && descriptor.disabled )
               descriptor.rejected = true;
         }
      }
   }

   /**
    * Opens the image preview dialog for a specific frame.
    *
    * @param {Object} frame - ActiveFrame object with 'current' property containing file path
    */
   showImagePreview( frame )
   {
      if ( !frame || !frame.current )
         return;

      let previewDialog = new WBPPImagePreviewDialog( frame.current );
      previewDialog.execute();
   }

   /**
    * Sorts active frames based on the current sort criterion.
    * Returns a new sorted array. Note: sets __originalIndex__ on each frame object
    * for selection preservation across sort operations.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects
    * @returns {Array} Sorted array of frames with __originalIndex__ property
    */
   sortFrames( activeFrames )
   {
      if ( !activeFrames || activeFrames.length === 0 )
         return [];

      // Create a copy with original indices
      let sortedFrames = [];
      for ( let i = 0; i < activeFrames.length; i++ )
      {
         let frame = activeFrames[ i ];
         frame.__originalIndex__ = i;
         sortedFrames.push( frame );
      }

      // Get sort criterion from plots grid
      let metricKey = this.plotsGrid.getActiveSortMetricKey();

      // If sorting by index (metricKey is null), return in original order
      if ( metricKey === null )
         return sortedFrames;

      // Sort by the selected metric
      sortedFrames.sort( ( a, b ) =>
      {
         let descA = a.descriptor
            ||
            {};
         let descB = b.descriptor
            ||
            {};
         let valA = descA.hasOwnProperty( metricKey ) ? descA[ metricKey ] : null;
         let valB = descB.hasOwnProperty( metricKey ) ? descB[ metricKey ] : null;

         // Handle null/undefined/NaN values - push them to the end
         let aInvalid = ( valA === null || valA === undefined || isNaN( valA ) );
         let bInvalid = ( valB === null || valB === undefined || isNaN( valB ) );
         if ( aInvalid && bInvalid )
            return 0;
         if ( aInvalid )
            return 1;
         if ( bInvalid )
            return -1;

         return valA - valB;
      } );

      return sortedFrames;
   }

   /**
    * Updates the display with the current sort criterion.
    * Preserves frame selection by tracking the original index.
    */
   updateDisplayWithCurrentSort()
   {
      if ( !this.selectedGroup )
         return;

      // Get the currently selected frame's original index
      let selectedOriginalIndex = -1;
      if ( this.framesTable.selectedFrame && this.framesTable.selectedFrame.__originalIndex__ !== undefined )
         selectedOriginalIndex = this.framesTable.selectedFrame.__originalIndex__;
      else if ( this.framesTable.selectedIndex >= 0 )
         selectedOriginalIndex = this.framesTable.selectedIndex;

      // Get and sort frames
      let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );
      let sortedFrames = this.sortFrames( activeFrames );

      // Find the new index of the previously selected frame
      let newSelectedIndex = -1;
      if ( selectedOriginalIndex >= 0 )
      {
         for ( let i = 0; i < sortedFrames.length; i++ )
         {
            if ( sortedFrames[ i ].__originalIndex__ === selectedOriginalIndex )
            {
               newSelectedIndex = i;
               break;
            }
         }
      }

      // Update displays with sorted frames
      this.framesTable.setFrames( sortedFrames, newSelectedIndex >= 0 ? newSelectedIndex : 0 );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );

      // Update highlight
      if ( newSelectedIndex >= 0 )
         this.plotsGrid.setHighlightedIndex( newSelectedIndex );
   }

   /**
    * Saves filter config for the current group.
    * Stores the configuration in the group object itself.
    */
   saveCurrentGroupFilterConfig()
   {
      if ( !this.selectedGroup )
         return;
      this.selectedGroup.setFrameFilterConfig( this.filterPanel.getFilterConfigs() );
   }

   /**
    * Loads filter config for a group from the group object.
    *
    * @param {FrameGroup} group - The group to load config from
    * @returns {boolean} True if config was loaded, false if not found
    */
   loadGroupFilterConfig( group )
   {
      let configs = group.getFrameFilterConfig();
      if ( configs )
      {
         this.filterPanel.setFilterConfigs( configs );
         return true;
      }
      return false;
   }

   /**
    * Called when a group is selected in the groups table.
    * Only displays the group's frames - does NOT recalculate rejections.
    * Rejections are calculated at initialization and when filters change.
    *
    * @param {FrameGroup} group - The selected group
    */
   onGroupSelected( group )
   {
      // Save current group's filter config before switching
      this.saveCurrentGroupFilterConfig();

      this.selectedGroup = group;

      // Load filter config from the group (for UI display)
      // All groups have configs after initialization, but keep fallback for safety
      if ( !this.loadGroupFilterConfig( group ) )
      {
         // Fallback: compute and save default config if somehow missing
         let defaultConfigs = group.initializeDefaultFilterConfig();
         this.filterPanel.setFilterConfigs( defaultConfigs );
      }

      // Update custom formula valid and enabled state in plots grid and frames table
      // This is necessary when switching groups as the loaded config may differ
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );

      // Get active frames for this group (rejection state already computed)
      let activeFrames = this.getActiveFramesForGroup( group );

      // Sort frames according to current criterion
      let sortedFrames = this.sortFrames( activeFrames );

      // Update displays with existing rejection state (sorted)
      this.framesTable.setFrames( sortedFrames );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );

      // Select first frame if available and update UI state
      if ( sortedFrames.length > 0 )
      {
         this.framesTable.selectFrameByIndex( 0 );
         // Manually trigger frame selection handler since programmatic selection
         // doesn't fire the callback
         this.selectedFrame = sortedFrames[ 0 ];
         this.plotsGrid.setHighlightedIndex( 0 );
         this.disableFrameButton.enabled = true;
         this.updateDisableButtonText();
      }
      else
      {
         this.selectedFrame = undefined;
         this.disableFrameButton.enabled = false;
         this.updateDisableButtonText();
      }
   }

   /**
    * Called when a frame is selected in the frames table.
    *
    * @param {ActiveFrame} frame - The selected frame
    * @param {number} index - The index of the selected frame
    */
   onFrameSelected( frame, index )
   {
      this.selectedFrame = frame;
      this.plotsGrid.setHighlightedIndex( index );

      // Update disable/enable button state
      this.disableFrameButton.enabled = ( frame !== undefined );
      this.updateDisableButtonText();
   }

   /**
    * Imports a metric value from the currently selected frame into the filter.
    * Sets the threshold to the frame's value and enables the filter.
    *
    * @param {string} metricKey - The metric key (e.g., 'FWHM', 'eccentricity', 'custom')
    */
   importMetricFromSelectedFrame( metricKey )
   {
      if ( !this.selectedFrame )
      {
         console.warningln( "No frame selected - cannot import metric value." );
         return;
      }

      let descriptor = this.selectedFrame.descriptor;
      if ( !descriptor )
      {
         console.warningln( "Selected frame has no descriptor - cannot import metric value." );
         return;
      }

      // Special handling for PSFSignalWeight: use normalized value (0-1 range)
      // to match what is displayed in the table and charts
      let value;
      if ( metricKey === 'PSFSignalWeight' )
         value = descriptor.PSFSignalWeightNormalized;
      else
         value = descriptor.hasOwnProperty( metricKey ) ? descriptor[ metricKey ] : null;

      if ( value === null || value === undefined || isNaN( value ) )
      {
         console.warningln( "Selected frame has no value for metric '" + metricKey + "'." );
         return;
      }

      // Import the value into the filter panel
      this.filterPanel.importValueForMetric( metricKey, value );
   }

   /**
    * Updates the disable/enable button text based on the selected frame's state.
    */
   updateDisableButtonText()
   {
      if ( !this.selectedFrame )
      {
         this.disableFrameButton.text = "Disable Frame";
         this.disableFrameButton.icon = this.scaledResource( ":/browser/delete.png" );
         return;
      }

      let descriptor = this.selectedFrame.descriptor
         ||
         {};
      let isDisabled = descriptor.disabled || false;

      if ( isDisabled )
      {
         this.disableFrameButton.text = "Enable Frame";
         this.disableFrameButton.icon = this.scaledResource( ":/icons/ok.png" );
      }
      else
      {
         this.disableFrameButton.text = "Disable Frame";
         this.disableFrameButton.icon = this.scaledResource( ":/browser/delete.png" );
      }
   }

   /**
    * Toggles the disabled state of the currently selected frame.
    * Disabled frames are excluded from plots and statistics.
    */
   toggleFrameDisabledState()
   {
      if ( !this.selectedFrame || !this.selectedGroup )
         return;

      let descriptor = this.selectedFrame.descriptor;
      if ( !descriptor )
         return;

      // Toggle disabled state
      descriptor.disabled = !( descriptor.disabled || false );

      // Update button text
      this.updateDisableButtonText();

      // Remember current selection (by original index)
      let selectedOriginalIndex = -1;
      if ( this.selectedFrame.__originalIndex__ !== undefined )
         selectedOriginalIndex = this.selectedFrame.__originalIndex__;
      else if ( this.framesTable.selectedIndex >= 0 )
         selectedOriginalIndex = this.framesTable.selectedIndex;

      // Update displays
      let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );
      let sortedFrames = this.sortFrames( activeFrames );

      // Find the new index of the previously selected frame
      let newSelectedIndex = -1;
      if ( selectedOriginalIndex >= 0 )
      {
         for ( let i = 0; i < sortedFrames.length; i++ )
         {
            if ( sortedFrames[ i ].__originalIndex__ === selectedOriginalIndex )
            {
               newSelectedIndex = i;
               break;
            }
         }
      }

      // Update frames table and plots (preserving selection)
      this.framesTable.setFrames( sortedFrames, newSelectedIndex >= 0 ? newSelectedIndex : 0 );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );
      this.groupsTable.updateContent(); // Update disabled/rejected count

      // Update plot highlight to match preserved frame selection
      if ( newSelectedIndex >= 0 )
         this.plotsGrid.setHighlightedIndex( newSelectedIndex );
   }

   /**
    * Resets (re-enables) all disabled frames in the current group.
    */
   resetDisabledFrames()
   {
      if ( !this.selectedGroup )
         return;

      // Clear disabled flag on all frames in the current group
      let frames = this.selectedGroup.activeFrames();
      for ( let i = 0; i < frames.length; i++ )
      {
         let descriptor = frames[ i ].descriptor;
         if ( descriptor && descriptor.disabled )
            descriptor.disabled = false;
      }

      // Update button text
      this.updateDisableButtonText();

      // Update displays
      let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );
      let sortedFrames = this.sortFrames( activeFrames );
      this.framesTable.setFrames( sortedFrames, 0 );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );
      this.groupsTable.updateContent();

      // Update selection
      if ( sortedFrames.length > 0 )
      {
         this.selectedFrame = sortedFrames[ 0 ];
         this.plotsGrid.setHighlightedIndex( 0 );
         this.disableFrameButton.enabled = true;
      }
   }

   /**
    * Gets the active frames for a given group.
    * Uses the group's activeFrames() method to get properly constructed ActiveFrame objects
    * with correctly bound descriptors.
    *
    * @param {FrameGroup} group - The group to get frames for
    * @returns {Array} Array of ActiveFrame objects
    */
   getActiveFramesForGroup( group )
   {
      if ( !group )
         return [];

      // Use the group's activeFrames() method which properly constructs ActiveFrame objects
      // with descriptors bound to the correct associatedID
      return group.activeFrames();
   }

   /**
    * Applies current filter settings to the current group.
    * Called when any filter parameter changes.
    * Preserves the current frame selection.
    * Uses centralized FrameGroup.applyFilters() method.
    */
   applyFiltersToCurrentGroup()
   {
      if ( !this.selectedGroup )
         return;

      // Remember current frame selection (by original index)
      let selectedOriginalIndex = -1;
      if ( this.framesTable.selectedFrame && this.framesTable.selectedFrame.__originalIndex__ !== undefined )
         selectedOriginalIndex = this.framesTable.selectedFrame.__originalIndex__;

      // Save filter config to group
      this.saveCurrentGroupFilterConfig();

      // Update custom formula validity and enabled state in plots grid and frames table
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );

      // Get current filter configs from UI panel
      let filterConfigs = this.filterPanel.getFilterConfigs();

      // Apply filters using centralized FrameGroup method
      // This handles custom formula application and rejection state
      this.selectedGroup.applyFilters( filterConfigs );

      // Get active frames after filtering
      let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );

      // Sort frames according to current criterion
      let sortedFrames = this.sortFrames( activeFrames );

      // Find the new index of the previously selected frame
      let newSelectedIndex = -1;
      if ( selectedOriginalIndex >= 0 )
      {
         for ( let i = 0; i < sortedFrames.length; i++ )
         {
            if ( sortedFrames[ i ].__originalIndex__ === selectedOriginalIndex )
            {
               newSelectedIndex = i;
               break;
            }
         }
      }

      // Update displays, preserving frame selection
      this.framesTable.setFrames( sortedFrames, newSelectedIndex >= 0 ? newSelectedIndex : 0 );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );
      this.groupsTable.updateContent(); // Update rejected count (preserves group selection)

      // Update plot highlight to match preserved frame selection
      if ( newSelectedIndex >= 0 )
         this.plotsGrid.setHighlightedIndex( newSelectedIndex );
   }

   /**
    * Applies current filter settings to all groups.
    * Preserves the current selection.
    * Uses centralized FrameGroup.applyFilters() method.
    */
   applyFiltersToAllGroups()
   {
      // Remember current selections (by original index)
      let selectedOriginalIndex = -1;
      if ( this.framesTable.selectedFrame && this.framesTable.selectedFrame.__originalIndex__ !== undefined )
         selectedOriginalIndex = this.framesTable.selectedFrame.__originalIndex__;

      // Update custom formula validity and enabled state in plots grid and frames table
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );

      // Apply to all groups using centralized method
      // Get a fresh copy of filter configs for each group to ensure complete independence
      for ( let i = 0; i < this.groups.length; i++ )
      {
         let group = this.groups[ i ];

         // Get a fresh copy of current configs for this group (ensures deep copy)
         let groupConfigs = this.filterPanel.getFilterConfigs();

         // Store the config in the group object (setFrameFilterConfig also does deep copy)
         group.setFrameFilterConfig( groupConfigs );

         // Apply filters using centralized FrameGroup method
         // This handles custom formula application and rejection state
         group.applyFilters( groupConfigs );
      }

      // Update displays, preserving selection
      if ( this.selectedGroup )
      {
         let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );
         let sortedFrames = this.sortFrames( activeFrames );

         // Find the new index of the previously selected frame
         let newSelectedIndex = -1;
         if ( selectedOriginalIndex >= 0 )
         {
            for ( let i = 0; i < sortedFrames.length; i++ )
            {
               if ( sortedFrames[ i ].__originalIndex__ === selectedOriginalIndex )
               {
                  newSelectedIndex = i;
                  break;
               }
            }
         }

         this.framesTable.setFrames( sortedFrames, newSelectedIndex >= 0 ? newSelectedIndex : 0 );
         this.plotsGrid.setFrames( sortedFrames );

         // Update plot highlight to match preserved frame selection
         if ( newSelectedIndex >= 0 )
            this.plotsGrid.setHighlightedIndex( newSelectedIndex );
      }
      this.groupsTable.updateContent();

      console.noteln( "Applied filter configuration to all " + this.groups.length + " groups." );
   }

   /**
    * Applies the custom formula to the current group.
    * Recomputes custom metric values and updates displays.
    * Preserves the current frame selection.
    * Uses centralized FrameGroup.applyCustomFormula() method.
    */
   applyCustomFormulaToCurrentGroup()
   {
      if ( !this.selectedGroup )
         return;

      // Remember current frame selection (by original index)
      let selectedOriginalIndex = -1;
      if ( this.framesTable.selectedFrame && this.framesTable.selectedFrame.__originalIndex__ !== undefined )
         selectedOriginalIndex = this.framesTable.selectedFrame.__originalIndex__;

      let isValid = this.filterPanel.isCustomFormulaValid();
      let isEnabled = this.filterPanel.isCustomFormulaEnabled();

      // Update custom formula validity and enabled state in plots grid and frames table
      this.plotsGrid.setCustomFormulaValid( isValid );
      this.plotsGrid.setCustomFormulaEnabled( isEnabled );
      this.framesTable.setCustomFormulaValid( isValid );

      // Apply custom formula to compute values using centralized method
      let formula = this.filterPanel.getCustomFormula();
      if ( isValid && formula )
         this.selectedGroup.applyCustomFormula( formula );

      // Get updated active frames
      let activeFrames = this.getActiveFramesForGroup( this.selectedGroup );

      // Initialize custom filter threshold from computed data
      this.filterPanel.initializeCustomFromFrames( activeFrames );

      // Save filter config to group (including custom formula changes)
      this.saveCurrentGroupFilterConfig();

      // Get current filter configs and apply filters using centralized method
      let filterConfigs = this.filterPanel.getFilterConfigs();
      this.selectedGroup.applyFilters( filterConfigs );

      // Refresh active frames after filtering
      activeFrames = this.getActiveFramesForGroup( this.selectedGroup );

      // Sort frames according to current criterion
      let sortedFrames = this.sortFrames( activeFrames );

      // Find the new index of the previously selected frame
      let newSelectedIndex = -1;
      if ( selectedOriginalIndex >= 0 )
      {
         for ( let i = 0; i < sortedFrames.length; i++ )
         {
            if ( sortedFrames[ i ].__originalIndex__ === selectedOriginalIndex )
            {
               newSelectedIndex = i;
               break;
            }
         }
      }

      // Update displays, preserving frame selection
      this.framesTable.setFrames( sortedFrames, newSelectedIndex >= 0 ? newSelectedIndex : 0 );
      this.plotsGrid.setFrames( sortedFrames );
      this.filterPanel.updatePlotThresholds( this.plotsGrid );
      this.groupsTable.updateContent();

      // Update plot highlight to match preserved frame selection
      if ( newSelectedIndex >= 0 )
         this.plotsGrid.setHighlightedIndex( newSelectedIndex );
   }

   /**
    * Resets the dialog to its initial state.
    * Iterates through groups, applies default filters, and refreshes the UI.
    */
   reset()
   {
      // Reset each group: clear states and apply default filter configs
      for ( let i = 0; i < this.groups.length; i++ )
      {
         let group = this.groups[ i ];

         // Clear rejection and disabled states
         group.clearAllFrameStates();

         // Compute and apply default filter config (all filters disabled)
         group.initializeDefaultFilterConfig();

         // Apply filters (with all disabled, no frames will be rejected)
         group.applyFilters();
      }

      // Reset UI elements
      this.filterPanel.reset();
      this.plotsGrid.resetSortState();
      this.plotsGrid.setCustomFormulaValid( false );
      this.plotsGrid.setCustomFormulaEnabled( false );
      this.framesTable.resetSortIndicator();
      this.framesTable.setCustomFormulaValid( false );

      // Update groups table to show new rejection counts (should be 0)
      this.groupsTable.setGroups( this.groups );

      // Reload UI for first group
      if ( this.groups.length > 0 )
      {
         let firstGroup = this.groups[ 0 ];

         // Set filter panel from first group's default config
         this.filterPanel.setFilterConfigs( firstGroup.getFrameFilterConfig() );

         // Select and display first group
         this.groupsTable.selectGroup( firstGroup );
         this.selectedGroup = firstGroup;

         // Get and display frames
         let activeFrames = this.getActiveFramesForGroup( firstGroup );
         let sortedFrames = this.sortFrames( activeFrames );
         this.framesTable.setFrames( sortedFrames );
         this.plotsGrid.setFrames( sortedFrames );
         this.filterPanel.updatePlotThresholds( this.plotsGrid );

         // Select first frame if available
         if ( sortedFrames.length > 0 )
         {
            this.framesTable.selectFrameByIndex( 0 );
            this.selectedFrame = sortedFrames[ 0 ];
            this.plotsGrid.setHighlightedIndex( 0 );
         }
         else
         {
            this.selectedFrame = undefined;
         }
      }

      // Update button states
      this.disableFrameButton.enabled = this.selectedFrame !== undefined;
      this.updateDisableButtonText();
   }

   /**
    * Initializes the dialog with the provided groups.
    * Computes default filter configs for ALL groups and applies filters.
    * Uses centralized FrameGroup methods for filter application.
    */
   initialize()
   {
      // Initialize ALL groups: compute default configs if needed, then apply filters
      for ( let i = 0; i < this.groups.length; i++ )
      {
         let group = this.groups[ i ];

         // Clear rejection state only (NOT disabled - that persists)
         group.clearFrameRejectionState();

         // Load this group's saved filter configuration, or compute defaults
         let groupFilterConfigs = group.getFrameFilterConfig();
         if ( !groupFilterConfigs )
         {
            // No saved config: compute default from frame statistics and save
            groupFilterConfigs = group.initializeDefaultFilterConfig();
         }

         // Apply custom formula if present in the config
         for ( let j = 0; j < groupFilterConfigs.length; j++ )
         {
            if ( groupFilterConfigs[ j ].isCustomFormula && groupFilterConfigs[ j ].formula )
            {
               group.applyCustomFormula( groupFilterConfigs[ j ].formula );
               break;
            }
         }

         // Apply this group's filters
         group.applyFilters( groupFilterConfigs );
      }

      // Initialize filter panel from first group for display
      if ( this.groups.length > 0 )
      {
         let firstGroup = this.groups[ 0 ];
         // All groups now have configs after the loop above
         this.filterPanel.setFilterConfigs( firstGroup.getFrameFilterConfig() );

         // Initialize custom formula display if valid
         if ( this.filterPanel.isCustomFormulaValid() )
         {
            let activeFrames = this.getActiveFramesForGroup( firstGroup );
            this.filterPanel.initializeCustomFromFrames( activeFrames );
         }
      }

      // Set initial custom formula valid and enabled state in plots grid and frames table
      let isCustomValid = this.filterPanel.isCustomFormulaValid();
      let isCustomEnabled = this.filterPanel.isCustomFormulaEnabled();
      this.plotsGrid.setCustomFormulaValid( isCustomValid );
      this.plotsGrid.setCustomFormulaEnabled( isCustomEnabled );
      this.framesTable.setCustomFormulaValid( isCustomValid );

      // Update groups table to show rejection counts
      this.groupsTable.setGroups( this.groups );

      // Select first group if available
      if ( this.groups.length > 0 )
      {
         this.groupsTable.selectGroup( this.groups[ 0 ] );
         this.onGroupSelected( this.groups[ 0 ] );
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-FrameSelection.js - Released 2026-05-10T11:05:00Z
