// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-FrameSelectionParameters.js - Released 2026-05-10T11:05:00Z
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
 * This file contains shared controls for frame selection parameters.
 * These controls are used both in the main WBPP interface (for default settings)
 * and in the interactive FrameSelection dialog.
 *
 * Note: Core formula validation/evaluation/application logic is centralized
 * in the FrameGroup class (BPP-FrameGroup.js). The functions here delegate
 * to FrameGroup methods or are kept for UI control standalone validation.
 */

// ----------------------------------------------------------------------------
// Custom Formula Validation and Evaluation (UI helpers)
// ----------------------------------------------------------------------------

// NOTE: CustomFormulaVariables is defined in BPP-FrameGroup.js and shared globally.

// ----------------------------------------------------------------------------
// Shared Helper Functions for Filter Criterion Controls
// ----------------------------------------------------------------------------

/**
 * Sets the initial threshold value based on metric statistics.
 * Shared helper used by both WBPPFilterCriterionControl and WBPPCustomFormulaCriterionControl.
 *
 * @param {Object} metricDef - Metric definition with defaultCompare and decimals
 * @param {Edit} valueEdit - The value edit control to update
 * @param {number} minVal - Minimum value in data
 * @param {number} maxVal - Maximum value in data
 */
function setFilterInitialValue( metricDef, valueEdit, minVal, maxVal )
{
   // Set threshold based on default compare mode
   let value;
   if ( metricDef.defaultCompare === FrameFilterCompareMode.LESS_THAN )
      value = maxVal; // For "less than", start with max (accept all)
   else
      value = minVal; // For "greater than", start with min (accept all)

   if ( !isNaN( value ) && isFinite( value ) )
      valueEdit.text = value.toFixed( metricDef.decimals );
}

/**
 * Tests if a value passes a filter criterion.
 * Shared helper used by both WBPPFilterCriterionControl and WBPPCustomFormulaCriterionControl.
 *
 * @param {boolean} isEnabled - Whether the filter is enabled (checkbox checked)
 * @param {ComboBox} compareCombo - The comparison mode combo box
 * @param {Edit} valueEdit - The threshold value edit control
 * @param {number} value - Value to test
 * @param {boolean} extraSkipCondition - Additional condition to skip filtering (e.g., invalid formula)
 * @returns {boolean} True if passes (not rejected)
 */
function testFilterPassesValue( isEnabled, compareCombo, valueEdit, value, extraSkipCondition )
{
   if ( !isEnabled || extraSkipCondition )
      return true; // Filter disabled or extra skip condition met
   if ( value === null || value === undefined || isNaN( value ) )
      return true; // No value, don't reject

   let threshold = parseFloat( valueEdit.text );
   if ( isNaN( threshold ) )
      return true; // Invalid threshold, don't reject

   if ( compareCombo.currentItem === FrameFilterCompareMode.LESS_THAN )
      return value < threshold;
   else
      return value > threshold;
}

// ----------------------------------------------------------------------------

/**
 * Single filter criterion control.
 * Contains: checkbox, label, edit field, comparison dropdown.
 * This control is shared between the main GUI and the FrameSelection dialog.
 *
 * @param {Control} parent - Parent control
 * @param {Object} metricDef - Metric definition object
 * @param {number} [labelWidth] - Optional fixed width for the label (default: 110)
 */
var WBPPFilterCriterionControl = class extends Control
{
   constructor( parent, metricDef, labelWidth )
   {
      super( parent );

   this.metricDef = metricDef;

   let compareComboWidth = this.font.width( "> (greater than)" + "MMMM" );

   // Enable checkbox
   this.enableCheckBox = new CheckBox( this );
   this.enableCheckBox.checked = false;
   this.enableCheckBox.toolTip = "<p>Enable filtering by " + metricDef.name + "</p>";
   this.enableCheckBox.onCheck = ( checked ) =>
   {
      this.valueEdit.enabled = checked;
      this.compareCombo.enabled = checked;
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Label
   this.label = new Label( this );
   this.label.text = metricDef.name + ":";
   this.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   if ( labelWidth !== undefined )
      this.label.setFixedWidth( labelWidth );
   else
      this.label.setScaledFixedWidth( 110 );

   // Comparison dropdown
   this.compareCombo = new ComboBox( this );
   this.compareCombo.addItem( "< (less than)" );
   this.compareCombo.addItem( "> (greater than)" );
   this.compareCombo.currentItem = metricDef.defaultCompare;
   this.compareCombo.setFixedWidth( compareComboWidth );
   this.compareCombo.enabled = false;
   this.compareCombo.toolTip = "<p>Comparison mode: frames with values that don't meet the condition will be rejected.</p>";
   this.compareCombo.onItemSelected = ( index ) =>
   {
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Value edit
   this.valueEdit = new Edit( this );
   this.valueEdit.setScaledFixedWidth( 80 );
   this.valueEdit.enabled = false;
   this.valueEdit.toolTip = "<p>Threshold value for " + metricDef.name + "</p>";
   this.valueEdit.onEditCompleted = () =>
   {
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Import from frame button (hidden by default, shown in interactive dialog)
   this.importButton = new ToolButton( this );
   this.importButton.icon = this.scaledResource( ":/icons/align-bottom.png" );
   this.importButton.setScaledFixedSize( 20, 20 );
   this.importButton.toolTip = "<p>Import " + metricDef.name + " value from the currently selected frame.</p>"
      + "<p>This will set the threshold to the selected frame's value and enable the filter.</p>";
   this.importButton.visible = false; // Hidden by default
   this.importButton.onClick = () =>
   {
      if ( this.onImportFromFrame )
         this.onImportFromFrame( this.metricDef.key );
   };

   // Layout
   this.sizer = new HorizontalSizer;
   this.sizer.spacing = 4;
   this.sizer.add( this.enableCheckBox );
   this.sizer.add( this.label );
   this.sizer.add( this.compareCombo );
   this.sizer.addSpacing( 4 );
   this.sizer.add( this.valueEdit );
   this.sizer.add( this.importButton );
   this.sizer.addStretch();
   }

   /**
    * Gets the current filter configuration.
    *
    * @returns {Object} Filter configuration
    */
   getFilterConfig()
   {
      return {
         enabled: this.enableCheckBox.checked,
         key: this.metricDef.key,
         value: parseFloat( this.valueEdit.text ) || 0,
         compareMode: this.compareCombo.currentItem
      };
   }

   /**
    * Sets the filter configuration.
    *
    * @param {Object} config - Filter configuration
    */
   setFilterConfig( config )
   {
      if ( !config )
         return;
      this.enableCheckBox.checked = config.enabled || false;
      this.valueEdit.text = config.value !== undefined ? config.value.toFixed( this.metricDef.decimals ) : "";
      this.compareCombo.currentItem = config.compareMode !== undefined ? config.compareMode : this.metricDef.defaultCompare;
      this.valueEdit.enabled = this.enableCheckBox.checked;
      this.compareCombo.enabled = this.enableCheckBox.checked;
   }

   /**
    * Sets the initial threshold value based on metric statistics.
    *
    * @param {number} minVal - Minimum value in data
    * @param {number} maxVal - Maximum value in data
    */
   setInitialValue( minVal, maxVal )
   {
      setFilterInitialValue( this.metricDef, this.valueEdit, minVal, maxVal );
   }

   /**
    * Checks if a value passes this filter.
    *
    * @param {number} value - Value to test
    * @returns {boolean} True if passes (not rejected)
    */
   passesFilter( value )
   {
      return testFilterPassesValue( this.enableCheckBox.checked, this.compareCombo, this.valueEdit, value, false );
   }

   /**
    * Resets the filter to its default unchecked state.
    */
   reset()
   {
      this.enableCheckBox.checked = false;
      this.valueEdit.text = "";
      this.valueEdit.enabled = false;
      this.compareCombo.currentItem = this.metricDef.defaultCompare;
      this.compareCombo.enabled = false;
   }

   /**
    * Shows or hides the import from frame button.
    *
    * @param {boolean} show - True to show, false to hide
    */
   setImportButtonVisible( show )
   {
      this.importButton.visible = show;
   }

   /**
    * Imports a value from a frame, setting it as the threshold and enabling the filter.
    *
    * @param {number} value - The value to import
    */
   importValue( value )
   {
      if ( value === null || value === undefined || isNaN( value ) )
         return;

      // Set the value
      this.valueEdit.text = value.toFixed( this.metricDef.decimals );

      // Enable the filter if not already enabled
      if ( !this.enableCheckBox.checked )
      {
         this.enableCheckBox.checked = true;
         this.valueEdit.enabled = true;
         this.compareCombo.enabled = true;
      }

      // Notify of change
      if ( this.onFilterChanged )
         this.onFilterChanged();
   }
}

// ----------------------------------------------------------------------------

/**
 * Custom formula filter control with real-time validation.
 * Displays a text input with validation feedback.
 *
 * @param {Control} parent - Parent control
 * @param {Object} metricDef - Metric definition object
 * @param {number} [labelWidth] - Optional fixed width for the label (default: 110)
 */
var WBPPCustomFormulaCriterionControl = class extends Control
{
   constructor( parent, metricDef, labelWidth )
   {
      super( parent );

   this.metricDef = metricDef;
   this.isValid = false;

   let compareComboWidth = this.font.width( "> (greater than)" + "MMMM" );

   // Enable checkbox
   this.enableCheckBox = new CheckBox( this );
   this.enableCheckBox.checked = false;
   this.enableCheckBox.toolTip = "<p>Enable filtering by custom formula</p>";
   this.enableCheckBox.onCheck = ( checked ) =>
   {
      this.formulaEdit.enabled = checked;
      this.compareCombo.enabled = checked;
      this.valueEdit.enabled = checked && this.isValid;
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Label
   this.label = new Label( this );
   this.label.text = "Custom:";
   this.label.textAlignment = TextAlignment.Right | TextAlignment.VertCenter;
   if ( labelWidth !== undefined )
      this.label.setFixedWidth( labelWidth );
   else
      this.label.setScaledFixedWidth( 110 );

   // Formula edit
   this.formulaEdit = new Edit( this );
   this.formulaEdit.setFixedWidth( compareComboWidth ); // Aligns right edge with valueEdit in standard filter rows
   this.formulaEdit.enabled = false;
   this.formulaEdit.toolTip = "<p><b>Custom Formula Expression</b></p>"
      + "<p>Create a custom metric by combining frame quality variables with JavaScript expressions.</p>"
      + "<p><b>Available Variables</b> (case-insensitive):</p>"
      + "<ul>"
      + "<li><b>FWHM</b> – Full Width at Half Maximum (pixels)</li>"
      + "<li><b>Eccentricity</b> – Star eccentricity (0 = circular)</li>"
      + "<li><b>SNR</b> – Signal-to-Noise Ratio</li>"
      + "<li><b>PSFSignalWeight</b> – PSF Signal Weight image quality estimator</li>"
      + "<li><b>Median</b> – Median pixel value</li>"
      + "<li><b>Stars</b> – Number of detected stars</li>"
      + "</ul>"
      + "<p><b>JavaScript Functions & Operators:</b></p>"
      + "<p>Standard JavaScript math is supported:</p>"
      + "<ul>"
      + "<li>Arithmetic: <tt>+ - * / %</tt></li>"
      + "<li>Power: <tt>Math.pow(x, n)</tt></li>"
      + "<li>Square root: <tt>Math.sqrt(x)</tt></li>"
      + "<li>Logarithms: <tt>Math.log(x)</tt>, <tt>Math.log10(x)</tt></li>"
      + "<li>Trigonometry: <tt>Math.sin(x)</tt>, <tt>Math.cos(x)</tt>, etc.</li>"
      + "<li>Min/Max: <tt>Math.min(a, b)</tt>, <tt>Math.max(a, b)</tt></li>"
      + "<li>Absolute value: <tt>Math.abs(x)</tt></li>"
      + "</ul>"
      + "<p><b>Examples:</b></p>"
      + "<ul>"
      + "<li><tt>SNR / FWHM</tt></li>"
      + "<li><tt>(Stars * SNR) / Eccentricity</tt></li>"
      + "<li><tt>Math.log(PSFSignalWeight) * SNR</tt></li>"
      + "<li><tt>Math.sqrt(SNR) / (FWHM * Eccentricity)</tt></li>"
      + "</ul>";
   this.formulaEdit.onTextUpdated = ( text ) =>
   {
      // Restart validation timer
      this.validationTimer.stop();
      this.validationTimer.start();
   };

   // Validation indicator
   this.validationLabel = new Label( this );
   this.validationLabel.setScaledFixedWidth( 20 );
   this.validationLabel.textAlignment = TextAlignment.Center | TextAlignment.VertCenter;
   this.validationLabel.text = "";

   // Comparison dropdown
   this.compareCombo = new ComboBox( this );
   this.compareCombo.addItem( "< (less than)" );
   this.compareCombo.addItem( "> (greater than)" );
   this.compareCombo.currentItem = metricDef.defaultCompare;
   this.compareCombo.setFixedWidth( compareComboWidth );
   this.compareCombo.enabled = false;
   this.compareCombo.toolTip = "<p>Comparison mode for the custom formula result</p>";
   this.compareCombo.onItemSelected = ( index ) =>
   {
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Value edit (threshold)
   this.valueEdit = new Edit( this );
   this.valueEdit.setScaledFixedWidth( 80 );
   this.valueEdit.enabled = false;
   this.valueEdit.toolTip = "<p>Threshold value for the custom formula result</p>";
   this.valueEdit.onEditCompleted = () =>
   {
      if ( this.onFilterChanged )
         this.onFilterChanged();
   };

   // Import from frame button (hidden by default, shown in interactive dialog)
   this.importButton = new ToolButton( this );
   this.importButton.icon = this.scaledResource( ":/icons/align-bottom.png" );
   this.importButton.setScaledFixedSize( 20, 20 );
   this.importButton.toolTip = "<p>Import custom formula value from the currently selected frame.</p>"
      + "<p>This will set the threshold to the selected frame's computed custom value and enable the filter.</p>";
   this.importButton.visible = false; // Hidden by default
   this.importButton.onClick = () =>
   {
      if ( this.onImportFromFrame )
         this.onImportFromFrame( this.metricDef.key );
   };

   // Validation timer (debounce validation)
   let self = this;
   this.validationTimer = new Timer;
   this.validationTimer.interval = 0.3; // 300ms debounce
   this.validationTimer.periodic = false;
   this.validationTimer.onTimeout = function()
   {
      self.performValidation();
   };

   // Layout - first row: checkbox, label, formula, validation indicator
   let row1 = new HorizontalSizer;
   row1.spacing = 4;
   row1.add( this.enableCheckBox );
   row1.add( this.label );
   row1.add( this.formulaEdit );
   row1.add( this.validationLabel );
   row1.addStretch();

   let row2 = new HorizontalSizer;
   row2.spacing = 4;
   // Aligns compareCombo with standard rows: checkbox(19) + spacing(4+4) + label.width
   row2.addUnscaledSpacing( this.logicalPixelsToPhysical( 19 + 4 + 4 ) + this.label.width );
   row2.add( this.compareCombo );
   row2.addSpacing( 4 );
   row2.add( this.valueEdit );
   row2.add( this.importButton );
   row2.addStretch();

   this.sizer = new VerticalSizer;
   this.sizer.spacing = 4;
   this.sizer.add( row1 );
   this.sizer.add( row2 );
   }

   /**
    * Performs formula validation and updates UI feedback.
    */
   performValidation()
   {
      let formula = this.formulaEdit.text.trim();
      let result = WBPPUtils.validateExpression( formula, CustomFormulaVariables );

      this.isValid = result.valid;

      if ( formula.length === 0 )
      {
         this.validationLabel.text = "";
         this.validationLabel.toolTip = "";
      }
      else if ( result.valid )
      {
         this.validationLabel.text = "✓";
         this.validationLabel.foregroundColor = 0xFF81C784; // Green
         this.validationLabel.toolTip = "<p>Formula is valid</p>";
      }
      else
      {
         this.validationLabel.text = "✗";
         this.validationLabel.foregroundColor = 0xFFE57373; // Red
         this.validationLabel.toolTip = "<p>Invalid formula: " + result.error + "</p>";
      }

      // Enable/disable controls based on validity
      this.valueEdit.enabled = this.enableCheckBox.checked && this.isValid;

      if ( this.onFormulaValidated )
         this.onFormulaValidated( this.isValid );
      if ( this.onFilterChanged )
         this.onFilterChanged();
   }

   /**
    * Gets the current filter configuration.
    *
    * @returns {Object} Filter configuration
    */
   getFilterConfig()
   {
      return {
         enabled: this.enableCheckBox.checked && this.isValid,
         key: this.metricDef.key,
         value: parseFloat( this.valueEdit.text ) || 0,
         compareMode: this.compareCombo.currentItem,
         formula: this.formulaEdit.text.trim(),
         isCustomFormula: true
      };
   }

   /**
    * Sets the filter configuration.
    *
    * @param {Object} config - Filter configuration
    */
   setFilterConfig( config )
   {
      if ( !config )
         return;

      this.formulaEdit.text = config.formula || "";
      this.validationTimer.stop();
      this.enableCheckBox.checked = config.enabled || false;
      this.valueEdit.text = config.value !== undefined ? config.value.toFixed( this.metricDef.decimals ) : "";
      this.compareCombo.currentItem = config.compareMode !== undefined ? config.compareMode : this.metricDef.defaultCompare;

      // Validate and update UI state
      this.performValidation();
      this.formulaEdit.enabled = this.enableCheckBox.checked;
      this.compareCombo.enabled = this.enableCheckBox.checked;
   }

   /**
    * Gets the current formula with normalized variable names.
    *
    * @returns {string} The formula expression with normalized variable names
    */
   getFormula()
   {
      return WBPPUtils.normalizeFormulaVariables( this.formulaEdit.text.trim(), CustomFormulaVariables );
   }

   /**
    * Sets the initial threshold value based on computed statistics.
    *
    * @param {number} minVal - Minimum value in data
    * @param {number} maxVal - Maximum value in data
    */
   setInitialValue( minVal, maxVal )
   {
      setFilterInitialValue( this.metricDef, this.valueEdit, minVal, maxVal );
   }

   /**
    * Checks if a value passes this filter.
    *
    * @param {number} value - Value to test
    * @returns {boolean} True if passes (not rejected)
    */
   passesFilter( value )
   {
      return testFilterPassesValue( this.enableCheckBox.checked, this.compareCombo, this.valueEdit, value, !this.isValid );
   }

   /**
    * Resets the filter to its default unchecked state.
    */
   reset()
   {
      this.enableCheckBox.checked = false;
      this.formulaEdit.text = "";
      this.formulaEdit.enabled = false;
      this.valueEdit.text = "";
      this.valueEdit.enabled = false;
      this.compareCombo.currentItem = this.metricDef.defaultCompare;
      this.compareCombo.enabled = false;
      this.isValid = false;
      this.validationLabel.text = "";
      this.validationLabel.toolTip = "";
   }

   /**
    * Shows or hides the import from frame button.
    *
    * @param {boolean} show - True to show, false to hide
    */
   setImportButtonVisible( show )
   {
      this.importButton.visible = show;
   }

   /**
    * Imports a value from a frame, setting it as the threshold and enabling the filter.
    * Note: For custom formula, the filter is only enabled if the formula is valid.
    *
    * @param {number} value - The value to import
    */
   importValue( value )
   {
      if ( value === null || value === undefined || isNaN( value ) )
         return;

      // Set the value
      this.valueEdit.text = value.toFixed( this.metricDef.decimals );

      // Enable the filter if not already enabled and formula is valid
      if ( !this.enableCheckBox.checked && this.isValid )
      {
         this.enableCheckBox.checked = true;
         this.formulaEdit.enabled = true;
         this.valueEdit.enabled = true;
         this.compareCombo.enabled = true;
      }

      // Notify of change
      if ( this.onFilterChanged )
         this.onFilterChanged();
   }

   /**
    * Static helper to calculate the minimum width needed to render a label.
    * Uses the parent control's font to measure text width.
    *
    * @param {Control} parent - Parent control whose font will be used for measurement
    * @param {string} text - The label text to measure
    * @returns {number} The minimum width needed to render the label
    */
   static measureLabelWidth( parent, text )
   {
      return parent.font.width( text );
   }
}

// ----------------------------------------------------------------------------

/**
 * Shared filter panel containing all filter criteria including custom formula.
 * This control is used both in the main WBPP interface and in the FrameSelection dialog.
 *
 * @param {Control} parent - Parent control
 * @param {boolean} showTitle - Whether to show the title label (default: true)
 * @param {boolean} showApplyToAll - Whether to show the "Apply to All" button (default: true)
 */
var WBPPFrameSelectionFiltersControl = class extends Control
{
   constructor( parent, showTitle, showApplyToAll )
   {
      super( parent );

   showTitle = ( showTitle !== undefined ) ? showTitle : true;
   showApplyToAll = ( showApplyToAll !== undefined ) ? showApplyToAll : true;

   // Title
   if ( showTitle )
   {
      this.titleLabel = new Label( this );
      this.titleLabel.text = "Rejection Filters";
      this.titleLabel.textAlignment = TextAlignment.Left | TextAlignment.VertCenter;
      let font = this.titleLabel.font;
      font.bold = true;
      this.titleLabel.font = font;
   }

   // Reference to custom formula filter (for special handling)
   this.customFormulaFilter = null;
   this.updatingFromConfig = false;

   // Store reference for closures
   let self = this;

   // Calculate the maximum label width needed across all metrics (+ padding)
   let maxLabelWidth = FrameFilterMetricDefinitions
      .map( m => WBPPCustomFormulaCriterionControl.measureLabelWidth( this, m.isCustomFormula ? "Custom:" : m.name + ":" ) )
      .reduce( ( max, w ) => Math.max( max, w ), 0 ) + 8;

   // Create filter criteria
   this.filters = [];
   for ( let i = 0; i < FrameFilterMetricDefinitions.length; i++ )
   {
      let metricDef = FrameFilterMetricDefinitions[ i ];
      let filter;

      // Use special control for custom formula
      if ( metricDef.isCustomFormula )
      {
         filter = new WBPPCustomFormulaCriterionControl( this, metricDef, maxLabelWidth );
         filter.onFormulaValidated = ( isValid ) =>
         {
            // Recompute custom values when formula is validated
            if ( isValid && !this.updatingFromConfig && this.onFormulaChanged )
               this.onFormulaChanged();
         };
         this.customFormulaFilter = filter;
      }
      else
      {
         filter = new WBPPFilterCriterionControl( this, metricDef, maxLabelWidth );
      }

      filter.onFilterChanged = () =>
      {
         if ( !this.updatingFromConfig && this.onFilterChanged )
            this.onFilterChanged();
      };

      // Delegate import from frame to container
      filter.onImportFromFrame = function( metricKey )
      {
         if ( self.onImportFromFrame )
            self.onImportFromFrame( metricKey );
      };

      this.filters.push( filter );
   }

   // Apply to All Groups button (optional)
   if ( showApplyToAll )
   {
      this.applyToAllButton = new PushButton( this );
      this.applyToAllButton.text = "Apply to All Groups";
      this.applyToAllButton.icon = this.scaledResource( ":/icons/copy.png" );
      this.applyToAllButton.toolTip = "<p>Apply the current filter configuration to all frame groups.</p>";
      this.applyToAllButton.onClick = () =>
      {
         if ( this.onApplyToAll )
            this.onApplyToAll();
      };
   }

   // Layout
   this.sizer = new VerticalSizer;
   this.sizer.spacing = 6;
   if ( showTitle )
   {
      this.sizer.add( this.titleLabel );
      this.sizer.addSpacing( 4 );
   }
   for ( let i = 0; i < this.filters.length; i++ )
      this.sizer.add( this.filters[ i ] );
   if ( showApplyToAll )
   {
      this.sizer.addSpacing( 8 );
      this.sizer.add( this.applyToAllButton );
   }
   this.sizer.addStretch();
   }

   /**
    * Gets the current custom formula.
    *
    * @returns {string} The custom formula expression
    */
   getCustomFormula()
   {
      if ( this.customFormulaFilter )
         return this.customFormulaFilter.getFormula();
      return "";
   }

   /**
    * Checks if the custom formula is valid.
    *
    * @returns {boolean} True if valid
    */
   isCustomFormulaValid()
   {
      if ( this.customFormulaFilter )
         return this.customFormulaFilter.isValid;
      return false;
   }

   /**
    * Checks if the custom formula filter is enabled (checkbox checked).
    *
    * @returns {boolean} True if enabled
    */
   isCustomFormulaEnabled()
   {
      if ( this.customFormulaFilter )
         return this.customFormulaFilter.enableCheckBox.checked;
      return false;
   }

   /**
    * Applies the custom formula to all frames in a group.
    * Updates the 'custom' key in each frame's descriptor.
    *
    * @param {FrameGroup} group - The frame group
    */
   applyCustomFormulaToGroup( group )
   {
      if ( !this.customFormulaFilter || !this.customFormulaFilter.isValid )
         return false;

      let formula = this.getCustomFormula();
      return group.applyCustomFormula( formula );
   }

   /**
    * Gets all filter configurations.
    *
    * @returns {Array} Array of filter configurations
    */
   getFilterConfigs()
   {
      let configs = [];
      for ( let i = 0; i < this.filters.length; i++ )
         configs.push( this.filters[ i ].getFilterConfig() );
      return configs;
   }

   /**
    * Sets all filter configurations.
    *
    * @param {Array} configs - Array of filter configurations
    */
   setFilterConfigs( configs )
   {
      if ( !configs )
         return;

      this.updatingFromConfig = true;
      try
      {
         for ( let i = 0; i < this.filters.length && i < configs.length; i++ )
            this.filters[ i ].setFilterConfig( configs[ i ] );
      }
      finally
      {
         this.updatingFromConfig = false;
      }
   }

   /**
    * Computes the min/max range of a metric across all frames and initializes
    * the filter with these bounds.
    *
    * @param {Object} filter - The filter object to initialize
    * @param {string} key - The descriptor key to extract values from
    * @param {Array} activeFrames - Array of ActiveFrame objects
    */
   initializeFilterFromFrames( filter, key, activeFrames )
   {
      let minVal = Infinity,
         maxVal = -Infinity;

      for ( let j = 0; j < activeFrames.length; j++ )
      {
         let descriptor = activeFrames[ j ].descriptor
            ||
            {};
         let value = descriptor.hasOwnProperty( key ) ? descriptor[ key ] : null;
         if ( value !== null && value !== undefined && !isNaN( value ) )
         {
            if ( value < minVal ) minVal = value;
            if ( value > maxVal ) maxVal = value;
         }
      }

      if ( isFinite( minVal ) && isFinite( maxVal ) )
         filter.setInitialValue( minVal, maxVal );
   }

   /**
    * Initializes filter value ranges from frame data statistics.
    *
    * This function scans all provided frames to determine the actual min/max
    * range of each metric, then uses these values to set the initial filter
    * boundaries. This allows filters to be pre-populated with meaningful
    * ranges based on the real data distribution.
    *
    * Frames with missing, null, undefined, or NaN values for a metric are
    * skipped during the min/max computation.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects, each containing
    *        a 'descriptor' property with metric values (e.g., FWHM, eccentricity,
    *        SNRWeight, etc.)
    */
   initializeFromFrames( activeFrames )
   {
      for ( let i = 0; i < this.filters.length; i++ )
      {
         let metricDef = this.filters[ i ].metricDef;

         // Skip custom formula - it needs formula to be set first
         if ( metricDef.isCustomFormula )
            continue;

         this.initializeFilterFromFrames( this.filters[ i ], metricDef.key, activeFrames );
      }
   }

   /**
    * Initializes custom formula filter values from computed data.
    *
    * @param {Array} activeFrames - Array of ActiveFrame objects with computed custom values
    */
   initializeCustomFromFrames( activeFrames )
   {
      if ( !this.customFormulaFilter || !this.customFormulaFilter.isValid )
         return;

      this.initializeFilterFromFrames( this.customFormulaFilter, "custom", activeFrames );
   }

   /**
    * Tests a frame against all enabled filters.
    *
    * @param {Object} descriptor - Frame descriptor with metric values
    * @returns {boolean} True if frame passes all filters (not rejected)
    */
   testFrame( descriptor )
   {
      for ( let i = 0; i < this.filters.length; i++ )
      {
         let key = this.filters[ i ].metricDef.key;
         let value = ( descriptor && descriptor.hasOwnProperty( key ) ) ? descriptor[ key ] : null;
         if ( !this.filters[ i ].passesFilter( value ) )
            return false;
      }
      return true;
   }

   /**
    * Resets all filters to their default unchecked state.
    */
   reset()
   {
      for ( let i = 0; i < this.filters.length; i++ )
         this.filters[ i ].reset();
   }

   /**
    * Check if any filter is enabled.
    *
    * @returns {boolean} True if at least one filter is enabled
    */
   hasEnabledFilters()
   {
      for ( let i = 0; i < this.filters.length; i++ )
      {
         let config = this.filters[ i ].getFilterConfig();
         if ( config.enabled )
            return true;
      }
      return false;
   }

   /**
    * Shows or hides the import from frame buttons for all filters.
    * These buttons should be shown in the interactive dialog but hidden
    * in the default values panel (main GUI).
    *
    * @param {boolean} show - True to show, false to hide
    */
   setImportButtonsVisible( show )
   {
      for ( let i = 0; i < this.filters.length; i++ )
         this.filters[ i ].setImportButtonVisible( show );
   }

   /**
    * Imports a value into the filter for the specified metric key.
    * Sets the value as threshold and enables the filter.
    *
    * @param {string} metricKey - The metric key (e.g., 'FWHM', 'eccentricity', 'custom')
    * @param {number} value - The value to import
    */
   importValueForMetric( metricKey, value )
   {
      for ( let i = 0; i < this.filters.length; i++ )
      {
         if ( this.filters[ i ].metricDef.key === metricKey )
         {
            this.filters[ i ].importValue( value );
            break;
         }
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-FrameSelectionParameters.js - Released 2026-05-10T11:05:00Z
