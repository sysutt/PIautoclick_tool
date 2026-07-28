// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ActiveFrame.js - Released 2026-05-10T11:05:00Z
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
 * Active Frame object. An Active Frame is a File Item wrapper that keeps a reference
 * to the associatedID version of the File Item and wraps some processing functions along
 * with some supporting functions.
 *
 * @param {*} fileItem the file item the active frame refers to
 * @param {*} associatedID the associated id defining the FileItem version
 */
var ActiveFrame = class
{

   constructor( fileItem, associatedID )
   {
      // Store the references
      this.fileItem = fileItem;
      this.associatedID = getValidAssociatedID( associatedID );

      // sync
      this.sync();
   }

   /**
    * Invoked when a processing step has been performed successfully on this active item.
    * Internally, the corresponding FileItem version will be marked as successfully processed.
    *
    * @param {WBPPFrameProcessingStep} step step executed
    * @param {String} filePath processed output file
    * @param {String} associatedID optional associated ID override
    */
   processingSucceeded( step, filePath, associatedID )
   {
      let id =
         associatedID && associatedID.length > 0
         ? associatedID
         : this.associatedID;
      this.fileItem.processingSucceeded( step, filePath, id );
      this.sync();
   }

   /**
    * Mark the file as failed to process. Indicates that an error occurred.
    *
    * @param {String} associatedID optional associated ID override
    */
   processingFailed( associatedID )
   {
      let id =
         associatedID && associatedID.length > 0
         ? associatedID
         : this.associatedID;
      this.fileItem.processingFailed( id );
      this.sync();
   }

   /**
    * Checks if the current active frame has been processed.
    *
    */
   isProcessed()
   {
      let processed = this.fileItem.processed[ this.associatedID ];
      return processed != null && Object.keys( processed ).length > 0;
   }

   /**
    * Returns the file name of the current item.
    *
    */
   currentFileName()
   {
      let name = File.extractName( this.current );
      let ext = File.extractExtension( this.current );

      return name + ext;
   }

   /**
    * Stores the descriptor associated to the current Active Frame.
    *
    * @param {*} descriptor the descriptor to be stored
    */
   setDescriptor( descriptor )
   {
      this.fileItem.descriptor[ this.associatedID ] = descriptor;
      this.sync();
   }

   /**
    * Stores the local normalization file for the associated ID
    *
    * @param {*} filePath the local normalization file
    */
   addLocalNormalizationFile( filePath )
   {
      this.fileItem.addLocalNormalizationFile( filePath, this.associatedID );
      this.sync();
   }

   /**
    * Stores the drizzle file for the associated ID
    *
    * @param {*} filePath the drizzle file
    */
   addDrizzleFile( filePath )
   {
      this.fileItem.addDrizzleFile( filePath, this.associatedID );
      this.sync();
   }

   /**
    * Marks the current associated File Item as a reference frame.
    *
    */
   markAsReference()
   {
      this.fileItem.markAsReference( this.associatedID );
      this.sync();
   }

   /**
    * Synchronize the active item with the corresponding fileItem version.
    *
    */
   sync()
   {
      // extract and inject the descriptor and the current item in the active frame
      // current is used to refer to the current file path
      this.current = this.fileItem.current[ this.associatedID ];
      // binning and descriptor is used when searching for the best reference frame
      this.binning = this.fileItem.binning;
      this.descriptor = this.fileItem.descriptor[ this.associatedID ];
      // exposure time is used to compute the active frame's total integration time
      this.exposureTime = this.fileItem.exposureTime;
      // get the associated local normalization file
      this.localNormalizationFile =
         this.fileItem.localNormalizationFile[ this.associatedID ];
      // get the associated drizzle file
      this.drizzleFile = this.fileItem.drizzleFile[ this.associatedID ];
      // track if the current active item was used as reference
      this.isReference = this.fileItem.isReference[ this.associatedID ];
      // sync the solver parameters
      this.solverParams = this.fileItem.solverParams;
      // fast integration is in sync only for light frames and for frames that are not an associated channel,
      // otherwise is disabled
      if (
         this.associatedID == BPP.Defaults.associatedId
         && this.fileItem.imageType == ImageType.Light
      )
         this.__fastIntegration = this.fileItem.__fastIntegration;
      else this.__fastIntegration = false;
   }

   /**
    * Creates a dummy active frame programmatically referencing a file on the disk.
    * This dummy active frame must be used for accessory operations only and must never
    * be used as a concrete instance referencing a real FileItem.
    *
    * @param {*} filePath the file path on disk
    * @param {*} cloneFrom optional ActiveFrame to clone properties from
    */
   static dummy( filePath, cloneFrom )
   {
      let imageType = ImageType.Light;
      let filter = "NoFilter";
      let binning = 1;
      let exposure = 0;
      let fileKeywords = {};
      let size = {
         width: 0,
         height: 0
      };
      let isCFA = false;
      let isMaster = false;
      let keywords = {};
      let solverParams = {};
      let overscan;
      if ( cloneFrom != undefined )
      {
         imageType = cloneFrom.imageType;
         filter = cloneFrom.filter;
         binning = cloneFrom.binning;
         exposure = cloneFrom.exposure;
         fileKeywords = cloneFrom.fileKeywords;
         size = cloneFrom.size;
         isCFA = cloneFrom.isCFA;
         isMaster = cloneFrom.isMaster;
         keywords = cloneFrom.keywords;
         solverParams = cloneFrom.solverParams;
         overscan = cloneFrom.overscan;
      }

      let fileItem = new FileItem(
         filePath,
         imageType,
         filter,
         binning,
         exposure,
         fileKeywords,
         size,
         undefined /* matching sizes */ ,
         isCFA,
         isMaster,
         keywords,
         solverParams,
         overscan
      );

      return new ActiveFrame( fileItem );
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-ActiveFrame.js - Released 2026-05-10T11:05:00Z
