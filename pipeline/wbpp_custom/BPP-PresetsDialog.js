// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-PresetsDialog.js - Released 2026-05-10T11:05:00Z
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
 * Dialog for selecting quality presets. Presents three quality tiers
 * (maximum, mid, fast) and returns the selected preset identifier.
 */
var PresetsDialog = class extends Dialog
{
   constructor()
   {
      super();
      this.windowTitle = "Presets";

      this.sizer = new VerticalSizer;
      this.sizer.margin = 8;
      this.sizer.spacing = 8;

      // MAX QUALITY
      this.addPreset(
         "Maximum quality",
         "<p><b>Maximum quality with no compromises.</b><br/>"
         + "Local normalization is enabled with its default maximum number of stars used for scale evaluation, "
         + "the PSF type is set to <i>Auto</i>.</p>",
         BPP.Presets.BEST_QUALITY
      );

      // FASTER / MID QUALITY
      this.addPreset(
         "Faster with good quality",
         "<p><b>Faster with sub-optimal quality results.</b><br/>"
         + "Local normalization is enabled with a reduced number of stars used for scale evaluation (500), "
         + "the PSF type is set to <i>Moffat 4</i>.</p>",
         BPP.Presets.MID
      );

      // FASTEST / LOW QUALITY
      this.addPreset(
         "Fastest with lower quality",
         "<p><b>Fastest method with lower quality results.</b><br/>"
         + "Local normalization is disabled.</p>",
         BPP.Presets.FAST
      );

      this.ensureLayoutUpdated();
      this.setFixedSize();
   }

   /**
    * Creates a preset entry with a title, description, and an APPLY button
    * that closes the dialog returning the preset identifier.
    *
    * @param {string} title - Display title for the preset section
    * @param {string} description - Rich-text description of the preset
    * @param {number} preset - Preset identifier returned when selected
    */
   addPreset = ( title, description, preset ) =>
   {
      let control = new ParametersControl( title, this );
      control.setScaledFixedWidth( 400 );

      let label = new Label( control );
      label.wordWrapping = true;
      label.useRichText = true;
      label.text = description;

      let button = new PushButton( control );
      button.text = "APPLY";
      button.onClick = () =>
      {
         this.done( preset );
      }
      let sizer = new HorizontalSizer;
      sizer.addStretch();
      sizer.add( button );
      sizer.addStretch();

      control.add( label );
      control.add( sizer );
      this.sizer.add( control );
   };
}

// ----------------------------------------------------------------------------
// EOF BPP-PresetsDialog.js - Released 2026-05-10T11:05:00Z
