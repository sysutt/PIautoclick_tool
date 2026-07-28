// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Diagnostic.js - Released 2026-05-10T11:05:00Z
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

var DiagnosticsManager = class
{
   constructor( engine )
   {
      this.engine = engine;
   }

   // ........................................................................
   // Static prefix/postfix constants for message formatting
   // ........................................................................

   static get errorPrefix()
   {
      return "<span style=\"color:#DD1111;\"><b>Error</b>: ";
   }

   static get errorPostfix()
   {
      return "</span>";
   }

   static get warningPrefix()
   {
      return "<span style=\"color:#CC00CC;\"><b>Warning</b>: ";
   }

   static get warningPostfix()
   {
      return "</span>";
   }

   static get notePrefix()
   {
      return "<span style=\"color:#009900;\"><b>Note</b></span>: <span style=\"white-space:break-spaces;\">";
   }

   static get notePostfix()
   {
      return "</span>";
   }

   // ........................................................................

   /**
    * Empty hook method for group status updates.
    * Overridden at runtime by the GUI layer.
    */
   postGroupStatus()
   {}

   // ........................................................................

   /**
    * Diagnostic messages generator.
    */
   runDiagnostics()
   {
      let engine = this.engine;

      this.messages = [ 0 ];

      this.pushTop = () =>
      {
         this.messages.push( engine.diagnosticMessages.length );
      };
      this.top = () =>
      {
         return this.messages[ this.messages.length - 1 ];
      };
      this.popTop = () =>
      {
         if ( this.messages.length > 1 )
            this.messages.pop();
      };

      let preprocessGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
      let postprocessGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST );

      /**
       * Removes all messages that are not errors or warnings until an error or warning is retrieved or
       * the top pointer is reached.
       */
      this.cleanUp = () =>
      {
         while ( this.top() < engine.diagnosticMessages.length && engine.diagnosticMessages.length > 0 )
         {
            let msg = engine.diagnosticMessages[ engine.diagnosticMessages.length - 1 ];
            if ( !msg.startsWith( DiagnosticsManager.errorPrefix ) && !msg.startsWith( DiagnosticsManager.warningPrefix ) && !msg.startsWith( DiagnosticsManager.notePrefix ) )
               engine.diagnosticMessages.pop();
            else
               return;
         }
      };

      /**
       * Pushes an error message
       *
       * @param {*} message the error message
       */
      this.error = function( message )
      {
         engine.diagnosticMessages.push( DiagnosticsManager.errorPrefix + "<i>" + message + "</i>." + DiagnosticsManager.errorPostfix );
      };

      /**
       * Pushes a warning message.
       *
       * @param {*} message the warning message
       */
      this.warning = function( message )
      {
         engine.diagnosticMessages.push( DiagnosticsManager.warningPrefix + "<i>" + message + "</i>." + DiagnosticsManager.warningPostfix );
      };

      /**
       * Pushes a note message.
       *
       * @param {*} message the note message
       */
      this.note = function( message )
      {
         engine.diagnosticMessages.push( DiagnosticsManager.notePrefix + message + "." + DiagnosticsManager.notePostfix );
      };

      /**
       * Adds a generic text to the diagnostic, appending a period at the end.
       *
       * @param {*} text
       */
      this.genericText = function( text )
      {
         engine.diagnosticMessages.push( text + "." );
      };

      /**
       * Adds a header
       *
       * @param {*} text the header title
       */
      this.headerText = function( text )
      {
         engine.diagnosticMessages.push( "<br><br><b>==== " + text + "</b>" );
      };

      // initial clean up
      this.clearDiagnosticMessages();

      // ........................................................................
      this.pushTop();
      this.headerText( "Check for long file path limitation" );
      if ( engine.outputDirectory != "" && File.directoryExists( engine.outputDirectory ) )
      {
         let foldersList = [ engine.outputDirectory ];
         while ( true )
         {
            foldersList.push( "WBPP_64_characters_folder_name_to_test_long_path_accessibility_" );
            let curDir = foldersList.join( "/" );
            try
            {
               File.createDirectory( curDir, true /* create intermediate dir */ );
            }
            catch ( e )
            {
               this.warning( "Cannot create files with a <b>path longer than 256 characters</b>. This is a limitation imposed by the "
                  + "operating system and can cause the failure of one or more steps.<br>"
                  + "Ensure that you remove this limitation by properly configuring your operating system settings." );
               break;
            }
            if ( curDir.length > 260 )
               break;
         }

         // clean up
         while ( foldersList.length > 1 )
         {
            let curDir = foldersList.join( "/" );
            try
            {
               File.removeDirectory( curDir );
            }
            catch ( e )
            {};
            foldersList.pop();
         }
      }
      this.cleanUp();
      this.popTop();

      // ........................................................................

      this.pushTop();
      this.headerText( "Check XISF writer" );
      try
      {
         let F = new FileFormat( ".xisf", false /*toRead*/ , true /*toWrite*/ );
         if ( F == null )
            throw '';
         if ( !F.canStoreFloat )
            this.error( "The " + F.name + " format cannot store 32-bit floating point image data" );
         if ( !F.canStoreKeywords )
            this.warning( "The " + F.name + " format does not support keywords" );
         if ( !F.canStoreProperties || !F.supportsViewProperties )
            this.warning( "The " + F.name + " format does not support image properties" );
         if ( F.isDeprecated )
            this.warning( "Using a deprecated output file format: " + F.name );

      }
      catch ( x )
      {
         this.error( "No installed file format can write .xisf files" );
      }
      this.cleanUp();
      this.popTop();

      // ........................................................................

      this.pushTop();
      this.headerText( "Check output directory" );

      let hasOutputDirectoryIssue = false;

      if ( WBPPUtils.isEmptyString( engine.outputDirectory ) )
      {
         this.error( "No output directory specified" );
         hasOutputDirectoryIssue = true;
      }
      else if ( !File.directoryExists( engine.outputDirectory ) )
      {
         this.error( "The specified output directory does not exist: " + engine.outputDirectory );
         hasOutputDirectoryIssue = true;
      }
      else
      {
         try
         {
            let f = new File;
            let n = engine.outputDirectory + "/__pixinsight_checking__";
            for ( let u = 1;; ++u )
            {
               let nu = File.appendToName( n, u.toString() );
               if ( !File.exists( nu ) )
               {
                  n = nu;
                  break;
               }
            }
            f.createForWriting( n );
            f.close();
            File.remove( n );
         }
         catch ( x )
         {
            this.error( "Cannot access the output directory for writing: " + engine.outputDirectory );
            hasOutputDirectoryIssue = true;
         }
      }

      this.cleanUp();
      this.popTop();

      // ........................................................................

      this.pushTop();
      this.headerText( "Check bias/dark/flat/light groups" );

      // global configuration
      if ( preprocessGroups.length == 0 && postprocessGroups.length == 0 )
         this.error( "No input frames have been provided" );
      else
      {
         if ( !engine.hasBiasFrames() )
            this.note( "No bias frames have been provided" );

         if ( !engine.hasDarkFrames() )
            this.note( "No dark frames have been provided" );

         if ( !engine.hasFlatFrames() )
            this.note( "No flat frames have been provided" );

         if ( !engine.hasLightFrames( BPP.GroupingMode.PRE ) )
            this.note( "No light frames have been provided" );
      }

      this.cleanUp();
      this.popTop();

      // ........................................................................

      // Diagnostic pre-processes BIAS, DARK, FLAT and LIGHT frames
      let groupsOrder = [ ImageType.Bias, ImageType.Dark, ImageType.Flat, ImageType.Light ];

      for ( let k = 0; k < groupsOrder.length; ++k )
      {
         for ( let i = 0; i < preprocessGroups.length; ++i )
         {
            if ( preprocessGroups[ i ].imageType != groupsOrder[ k ] )
               continue;

            this.pushTop();
            this.headerText( preprocessGroups[ i ].toString() );

            // check file existence
            for ( let j = 0; j < preprocessGroups[ i ].fileItems.length; ++j )
               if ( !File.exists( preprocessGroups[ i ].fileItems[ j ].filePath ) )
                  this.error( "Nonexistent input file: " + preprocessGroups[ i ].fileItems[ j ].filePath );

            // filter name character set
            if ( !WBPPUtils.isEmptyString( preprocessGroups[ i ].filter ) )
               if ( WBPPUtils.cleanFilterName( preprocessGroups[ i ].filter ) != preprocessGroups[ i ].filter )
                  this.warning( "Invalid file name characters will be replaced with dashes "
                     + "in filter name: \'" + preprocessGroups[ i ].filter + "\'" );

            // various checks for flat and light frames
            if ( ( preprocessGroups[ i ].imageType == ImageType.Flat || preprocessGroups[ i ].imageType == ImageType.Light )
               && !preprocessGroups[ i ].hasMaster )
            {
               let cf = engine.calibrationMatcher.getCalibrationGroupsFor( preprocessGroups[ i ] )
               let masterDarkExposureDifferenceIsHigh = cf.masterDark && Math.abs( cf.masterDark.exposureTime - preprocessGroups[ i ].exposureTime ) > 5;

               // check if neither bias nor dark are available
               if ( !cf.masterBias && !cf.masterDark && !cf.masterFlat )
               {
                  this.note( "No Master Bias, Master Dark and Master Flat have been provided to calibrate this group. Frames will not be calibrated" );
                  continue;
               }

               // check if neither bias nor dark are available
               if ( !cf.masterBias && !cf.masterDark )
                  this.note( "Neither Master Bias nor Master Dark will be used to calibrate the frames" );

               // check if only dark is found but it does not contain the master bias
               if ( !cf.masterBias && cf.masterDark && preprocessGroups[ i ].optimizeMasterDark )
                  this.warning( "Frames will be calibrated using an optimized Master Dark but no Master Bias has been found. Optimizing a Master Dark without subtracting the Master Bias could (likely) lead to improper results" );

               // check if dark exposure difference is too much
               if ( masterDarkExposureDifferenceIsHigh )
               {
                  if ( preprocessGroups[ i ].optimizeMasterDark )
                     this.note( 'Frames will be calibrated using an optimized Master Dark with an exposure time of ' + cf.masterDark.exposureTime + ' sec' );
                  else
                     this.warning( 'Frames will be calibrated using a Master Dark with a non-matching exposure time of ' + cf.masterDark.exposureTime + ' sec' );
               }

               // check CC parameters
               if ( preprocessGroups[ i ].imageType == ImageType.Light )
               {
                  let ccWarning = preprocessGroups[ i ].validateCC( cf.masterDark );
                  if ( ccWarning )
                     this.warning( ccWarning );

                  // Cosmetic correction check
                  if ( preprocessGroups[ i ].ccData.CCTemplate && preprocessGroups[ i ].ccData.CCTemplate.length > 0 )
                  {
                     let CC = ProcessInstance.fromIcon( preprocessGroups[ i ].ccData.CCTemplate );
                     if ( CC == null )
                        this.warning( "Missing Cosmetic Correction process icon: " + preprocessGroups[ i ].ccData.CCTemplate );
                     else
                     {
                        if ( !( CC instanceof CosmeticCorrection ) )
                           this.warning( "The specified process icon does not transport an instance "
                              + "of Cosmetic Correction: " + preprocessGroups[ i ].ccData.CCTemplate );
                        else
                        {
                           if ( !CC.useMasterDark && !CC.useAutoDetect && !CC.useDefectList )
                              this.warning( "The specified Cosmetic Correction instance does not define "
                                 + "a valid correction operation: " + preprocessGroups[ i ].ccData.CCTemplate );
                        }
                     }
                  }

                  // check flats for light frames
                  if ( !cf.masterFlat )
                     this.note( "No Master Flat will be used to calibrate the frames" );

               }
            }

            // ----------------------------------------

            // check rejection for bias/dark/flat groups that do not have a master (so they will be integrated)
            if ( preprocessGroups[ i ].imageType != ImageType.Light && !preprocessGroups[ i ].hasMaster )
            {
               let r = preprocessGroups[ i ].rejectionIsGood( engine.rejection[ BPP.imageTypeIndex( preprocessGroups[ i ].imageType ) ] );
               if ( !r[ 0 ] ) // if not good
                  this.warning( "Integration of " + preprocessGroups[ i ].toString() + ": " + r[ 1 ] ); // reason
            }

            this.cleanUp();
            this.popTop();
         }
      }

      this.pushTop();
      this.headerText( "Check registration configuration" );

      // ----------------------------------------

      if ( !engine.imageRegistration && engine.integrate )
      {
         this.warning( "You decided to integrate your light frames but registration is disabled. "
            + "Ensure that your light frames are already aligned or enable the registration to properly "
            + "align them before generating the master light frames" );
      }

      // ----------------------------------------

      if ( engine.imageRegistration && engine.reuseLastReferenceFrames )
      {
         let failed = false;
         for ( let i = 0; i < postprocessGroups.length; ++i )
         {
            if ( postprocessGroups[ i ].__reference_frame__ == undefined )
            {
               failed = true;
               this.error( "Missing last registration reference frame for group <b>" + postprocessGroups[ i ].toString() + "</b>" );
            }
            else
            {
               if ( !File.exists( postprocessGroups[ i ].__reference_frame__ ) )
               {
                  failed = true;
                  this.error( "Last registration reference frame <b>[" + postprocessGroups[ i ].__reference_frame__ + "]</b> not found for group <b>" + postprocessGroups[ i ].toString() + "</b>" );
               }
            }
         }
         if ( failed )
            this.error( "<b>WBPP needs to be executed first using a registration mode to assign a reference frame to all groups</b>" );
      }

      this.cleanUp();
      this.popTop();

      // ----------------------------------------

      this.pushTop();
      this.headerText( "Check local normalization configuration" );

      if ( engine.localNormalization && engine.reuseLastLNReferenceFrames )
      {
         let failed = false;
         for ( let i = 0; i < postprocessGroups.length; ++i )
         {
            if ( postprocessGroups[ i ].__ln_reference_frame__ == undefined )
            {
               failed = true;
               this.error( "Missing last local normalization reference frame for group <b>" + postprocessGroups[ i ].toString() + "</b>" );
            }
            else
            {
               if ( !File.exists( postprocessGroups[ i ].__ln_reference_frame__ ) )
               {
                  failed = true;
                  this.error( "Last local normalization reference frame <b>[" + postprocessGroups[ i ].__ln_reference_frame__ + "]</b> not found for group <b>" + postprocessGroups[ i ].toString() + "</b>" );
               }
            }
         }
         if ( failed )
            this.error( "<b>WBPP needs to be executed first enabling local normalization to assign a local normalization reference frame to all groups</b>" );
      }

      this.cleanUp();
      this.popTop();

      // ----------------------------------------
      this.pushTop();
      this.headerText( "Check weights configuration" );

      if ( engine.subframesWeightsMethod == BPP.SubframeWeightsMethod.PSFScaleSNR
         && engine.integrate
         && !engine.localNormalization )
      {
         this.error( "The integration of light frames using the PSF Scale SNR weighting method requires Local Normalization to be enabled" )
      }

      this.cleanUp();
      this.popTop();

      // ----------------------------------------

      for ( let i = 0; i < postprocessGroups.length; ++i )
      {
         if ( postprocessGroups[ i ].imageType != ImageType.Light )
            continue;

         this.pushTop();
         this.headerText( postprocessGroups[ i ].toString() );

         let needsIntegration = postprocessGroups[ i ].associatedRGBchannel == undefined || postprocessGroups[ i ].associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB;

         if ( engine.integrate
            && needsIntegration
            && postprocessGroups[ i ].fileItems.length < 3 )
         {
            this.error( "Only " + postprocessGroups[ i ].fileItems.length + " frames provided. Cannot integrate less than 3 light frames" );
         }

         // check rejection for light post-processing groups if integration is enabled
         if ( engine.integrate
            && needsIntegration
            && postprocessGroups[ i ].imageType == ImageType.Light )
         {
            let r = postprocessGroups[ i ].rejectionIsGood( engine.rejection[ BPP.imageTypeIndex( postprocessGroups[ i ].imageType ) ] );
            if ( !r[ 0 ] ) // if not good
               this.warning( "Integration of " + postprocessGroups[ i ].toString() + ": " + r[ 1 ] ); // reason
         }

         // check if enough files are provided when drizzle integration is active
         if ( postprocessGroups[ i ].isDrizzleEnabled()
            && needsIntegration && postprocessGroups[ i ].fileItems.length < 15 )
         {
            this.warning( "Drizzle Integration of " + postprocessGroups[ i ].toString() + " (" + postprocessGroups[ i ].fileItems.length + "): drizzle requires more than 15 frames to produce optimal results" );
         }
         if ( postprocessGroups[ i ].isDrizzleEnabled() && postprocessGroups[ i ].fileItems.length > 40 && !postprocessGroups[ i ].drizzleFast() )
         {
            this.warning( "Drizzle Integration of " + postprocessGroups[ i ].toString() + " (" + postprocessGroups[ i ].fileItems.length + "): drizzling that amount of frames <b>may significantly impact the execution time</b>" );
         }
         this.cleanUp();
         this.popTop();
      }

      // ........................................................................

      // Check overscan
      if ( engine.overscan.enabled )
      {
         this.pushTop();
         this.headerText( "Check Overscan settings" );

         if ( !engine.overscan.isValid() )
            this.error( "Invalid overscan region(s) defined" );
         else if ( engine.overscan.enabled && !engine.overscan.hasOverscanRegions() )
            this.warning( "Overscan correction has been enabled, but no overscan regions have been defined" );

         this.cleanUp();
         this.popTop();
      }

      // ----------------------------------------

      // Reference frame
      if ( engine.hasLightFrames( BPP.GroupingMode.POST ) && !engine.reuseLastReferenceFrames )
      {
         this.pushTop();
         this.headerText( "Check reference frame settings" );

         // best reference frame checks
         if ( engine.imageRegistration )
         {
            if ( engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.MANUAL )
            {
               if ( WBPPUtils.isEmptyString( engine.referenceImage ) )
                  this.error( "No registration reference image has been specified." );
               else if ( !File.exists( engine.referenceImage ) )
                  this.error( "The specified registration reference file does not exist: " + engine.referenceImage );
            }
            else
            {
               let keywords = engine.keywords.keywordsForMode( BPP.GroupingMode.POST );
               if ( keywords.length > 0 && engine.bestFrameReferenceMethod == BPP.BestReferenceMethod.AUTO_SINGLE && engine.groupingKeywordsEnabled )
               {
                  let keywordsList = keywords.map( k => k.name ).join( ", " );
                  let kwDesc = keywords.length > 1 ? "s " + keywordsList + "s <b>" : " <b>" + keywordsList + "</b>";
                  this.warning( "Master Light frames will be grouped using the keyword" + kwDesc + " and the registration mode is <b>auto</b>: "
                     + "<u>All frames will be aligned on the same reference frame</u>. Consider selecting <b>\"auto by\"</b> registration mode "
                     + "if you want to register these groups separately by keyword" );
               }
            }
         }

         this.cleanUp();
         this.popTop();
      }

      // ----------------------------------------
      this.pushTop();
      this.headerText( "Check Autocrop configuration" );

      if ( engine.autocrop && !engine.generateRejectionMaps )
      {
         this.warning( "The global '<i>Generate rejection maps</i>' option will be ignored because the <b>Autocrop</b> feature has been selected, which depends on rejection maps" );
      }

      this.cleanUp();
      this.popTop();

      // ----------------------------------------

      // Pipeline script
      if ( engine.usePipelineScript && engine.pipelineScriptFile != "" )
      {
         this.headerText( "Checking pipeline script at path " + engine.pipelineScriptFile );
         let installResult = engine.operationQueue.installEventScript( engine.pipelineScriptFile );
         if ( typeof installResult != "boolean" )
            this.warning( "Check failed with error: " + installResult );
         else if ( installResult === false )
            this.warning( "Check failed" );
         else
            this.note( "Success" );
      }

      // ----------------------------------------
      // report the required space

      this.pushTop();
      this.headerText( "Check disk space availability" );

      // non zero-size keys
      let keys = Object.keys( engine.WS ).filter( key => ( engine.WS[ key ].size > 0 ) );
      // total space
      let WStot = keys.reduce( ( acc, key ) => ( acc + engine.WS[ key ].size ), 0 );
      // length of the longes non null label
      let pad = keys.reduce( ( acc, key ) => ( Math.max( acc, engine.WS[ key ].label.length ) ), 0 ) + 3;
      // generate the size report for each non null sized key
      keys.forEach( key =>
      {
         this.note( WBPPUtils.paddedLabel( engine.WS[ key ].label, pad ) + WBPPUtils.readableSize( engine.WS[ key ].size ) );
      } );

      // check if available space is enough
      if ( !hasOutputDirectoryIssue )
      {
         let availableSpace = File.getAvailableSpace( engine.outputDirectory );
         let readableWS = WBPPUtils.readableSize( WStot ).trim();
         let readableAvailableSpace = WBPPUtils.readableSize( availableSpace ).trim();
         if ( WStot > availableSpace )
            this.warning( "The required working space (" + readableWS + ") is more than the available space (" + readableAvailableSpace + ")" );
         else if ( WStot >= 0.95 * availableSpace )
            this.warning( "The required working space (" + readableWS + ") is close to the available space (" + readableAvailableSpace + ")" );
         else
            this.note( "The required working space is " + readableWS + " (available " + readableAvailableSpace + ")" );
      }

      this.cleanUp();
      this.popTop();
   }

   // ........................................................................

   /**
    * Returns true if there are diagnostic messages.
    *
    * @returns {Boolean} True if diagnostic messages are present, false otherwise.
    */
   hasDiagnosticMessages()
   {
      return this.engine.diagnosticMessages.length > 0;
   }

   // ........................................................................

   /**
    * Returns true if diagnostic contains error messages.
    *
    * @returns {Boolean} True if any error message is present, false otherwise.
    */
   hasErrorMessages()
   {
      for ( let i = 0; i < this.engine.diagnosticMessages.length; ++i )
         if ( this.engine.diagnosticMessages[ i ].startsWith( DiagnosticsManager.errorPrefix ) )
            return true;
      return false;
   }

   // ........................................................................

   /**
    * Removes all diagnostic messages.
    *
    */
   clearDiagnosticMessages()
   {
      this.engine.diagnosticMessages = new Array;
   }

   // ........................................................................

   /**
    * Shows the diagnostic messages dialog, optionally with a cancel button.
    *
    * @param {Boolean} cancelButton true if a cancel button needs to be shown
    * @param {Boolean} generateScreenshots true if a "Generate Screenshots" button should be displayed
    * @returns {Number} StdDialogCode.Cancel if errors are present or the user
    *          cancels, StdDialogCode.Ok if OK/Continue is pressed,
    *          BPP.Format.StdDialogCode_GenerateScreenshots if screenshots requested.
    */
   showDiagnosticMessages( cancelButton, generateScreenshots )
   {
      if ( this.hasErrorMessages() )
      {
         ( new DiagnosticInformationDialog( this.engine.diagnosticMessages, false /*cancelButton*/ , generateScreenshots ) ).execute();
         return StdDialogCode.Cancel;
      }

      return ( new DiagnosticInformationDialog( this.engine.diagnosticMessages, cancelButton, generateScreenshots ) ).execute();
   }
}

// ----------------------------------------------------------------------------

/**
 * Diagnostic messages dialog.
 *
 * @param {Array<String>} messages The array of diagnostic messages to be displayed.
 * @param {Boolean} cancelButton True if a Cancel button should be displayed.
 * @param {Boolean} generateScreenshots True if a "Generate Screenshots" button should be displayed.
 */
var DiagnosticInformationDialog = class extends Dialog
{
   constructor( messages, cancelButton, generateScreenshots )
   {
      super();

      let messagesCount = 0;
      let info = "<html>";
      for ( let i = 0; i < messages.length; ++i )
      {
         let line = messages[ i ].trim();
         info += line + "<br/>";
         if ( line.length > 0 )
            if ( !line.contains( "====" ) )
               messagesCount += 1;
      }
      info += "</html><beg>";

      this.infoLabel = new Label( this );
      this.infoLabel.text = format( "%d message(s):", messagesCount );
      this.infoLabel.adjustToContents();
      this.infoLabel.setMaxHeight( this.infoLabel.height );

      this.infoBox = new TextBox( this );
      this.infoBox.readOnly = true;
      this.infoBox.styleSheet = "pi--PixInsightConsole { "
         + "font-family: Hack, DejaVu Sans Mono, Monospace; font-size: 10pt; background: white; }";
      this.infoBox.setScaledMinSize( 800, 300 );
      this.infoBox.text = info;

      this.okButton = new PushButton( this );
      this.okButton.defaultButton = true;
      this.okButton.text = cancelButton ? "Continue" : "OK";
      this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
      this.okButton.onClick = function()
      {
         this.dialog.done( StdDialogCode.Ok );
      };

      if ( cancelButton )
      {
         this.cancelButton = new PushButton( this );
         this.cancelButton.defaultButton = true;
         this.cancelButton.text = "Cancel";
         this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
         this.cancelButton.onClick = function()
         {
            this.dialog.done( StdDialogCode.Cancel );
         };
      }

      if ( generateScreenshots )
      {
         this.screenshotsButton = new PushButton( this );
         this.screenshotsButton.defaultButton = true;
         this.screenshotsButton.text = "Generate Screenshots";
         this.screenshotsButton.icon = this.scaledResource( ":/icons/picture-export.png" );
         this.screenshotsButton.onClick = function()
         {
            this.dialog.done( BPP.Format.StdDialogCode_GenerateScreenshots );
         };
      }

      this.buttonsSizer = new HorizontalSizer;
      this.buttonsSizer.addStretch();
      this.buttonsSizer.add( this.okButton );
      if ( cancelButton )
      {
         this.buttonsSizer.addSpacing( 8 );
         this.buttonsSizer.add( this.cancelButton );
      }
      if ( generateScreenshots )
      {
         this.buttonsSizer.addSpacing( 8 );
         this.buttonsSizer.add( this.screenshotsButton );
      }

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

      this.windowTitle = "Diagnostic Messages";
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-Diagnostic.js - Released 2026-05-10T11:05:00Z
