// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ProcessLogDialog.js - Released 2026-05-10T11:05:00Z
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
 * Dialog for displaying and saving the process log.
 */
var ProcessLogDialog = class extends Dialog
{
   constructor( processLogger )
   {
      super();

      let info = processLogger.toString();

      this.infoLabel = new Label( this );
      this.infoLabel.text = "WBPP steps:";

      this.infoBox = new TextBox( this );
      this.infoBox.useRichText = true;
      this.infoBox.readOnly = true;
      this.infoBox.styleSheet = this.scaledStyleSheet( "pi--PixInsightConsole { "
         + "font-family: Hack, DejaVu Sans Mono, monospace; font-size: 10pt; padding: 4px; }" );
      this.infoBox.setScaledMinSize( 800, 300 );
      this.infoBox.text = info;

      this.saveButton = new PushButton( this );
      this.saveButton.text = "Save";
      this.saveButton.icon = this.scaledResource( ":/icons/save.png" );
      this.saveButton.onClick = () =>
      {
         // save content to a text file
         var save = new SaveFileDialog;
         save.caption = "Process Dialog Output File";
         save.initialPath = engine.outputDirectory + "/logs/ProcessLogger.txt";
         save.overwritePrompt = true;
         save.filters = [
            [ "*.txt", "*.*" ]
         ];

         if ( save.execute() )
            processLogger.writeToFile( save.filePath );
      };

      this.okButton = new PushButton( this );
      this.okButton.defaultButton = true;
      this.okButton.text = "DONE";
      this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
      this.okButton.onClick = () =>
      {
         this.ok();
      };

      this.buttonsSizer = new HorizontalSizer;
      this.buttonsSizer.addStretch();
      this.buttonsSizer.add( this.saveButton );
      this.buttonsSizer.addScaledSpacing( 8 );
      this.buttonsSizer.add( this.okButton );

      this.sizer = new VerticalSizer;
      this.sizer.margin = 8;
      this.sizer.add( this.infoLabel );
      this.sizer.addSpacing( 4 );
      this.sizer.add( this.infoBox );
      this.sizer.addSpacing( 8 );
      this.sizer.add( this.buttonsSizer );

      this.ensureLayoutUpdated();
      this.adjustToContents();
      this.setMinSize();

      this.windowTitle = "Smart Report";
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-ProcessLogDialog.js - Released 2026-05-10T11:05:00Z
