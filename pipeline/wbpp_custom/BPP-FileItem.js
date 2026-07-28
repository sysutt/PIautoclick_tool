// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-FileItem.js - Released 2026-05-10T11:05:00Z
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
 * Returns the provided ID if it's a non-empty string, otherwise returns the default ID
 * @param {String} [id] - The ID to validate
 * @returns {String} The validated ID or the default ID
 * @private
 */
function getValidAssociatedID( id )
{
   return ( id != null && typeof id === "string" && id.trim().length > 0 ) ? id.trim() : BPP.Defaults.associatedId;
}

/**
 * File Item constructor. A File Item references a file on disk along with all its processed versions.
 *
 * Smart naming has two tiers:
 * - Main metadata keywords (IMAGETYP, FILTER, BINNING, EXPTIME, etc.) are overridden
 *   by file path conventions only when smartNamingOverride was enabled at the time the
 *   file was added. This state is frozen in the createdWithSmartNamingEnabled property
 *   and persists across save/load cycles.
 * - Custom grouping keywords (user-defined via engine.keywords) are always extracted
 *   from the file path if present, regardless of the smartNamingOverride state.
 *
 * @param {String} filePath - The absolute or relative path to the image file
 * @param {ImageType} imageType - Type of image (e.g., LIGHT, DARK, FLAT, etc.)
 * @param {String} filter - Name of the filter used for the image
 * @param {Number} binning - Image's binning factor
 * @param {Number} exposureTime - Image's exposure time in seconds
 * @param {{String:String}} fileKeywords - Name-value map containing the file header metadata
 * @param {Object} size - Object containing image dimensions {width: Number, height: Number}
 * @param {Object} matchingSizes - Object containing reference sizes for different grouping modes
 *                                Format: {[groupingMode: String]: {width: Number, height: Number}}
 * @param {Boolean} isCFA - True if the file contains a Color Filter Array (CFA) image
 * @param {Boolean} isMaster - True if the image is a master calibration file
 * @param {{String:String}?} keywords - Custom keywords key-value map
 * @param {Object?} solverParams - Solver parameters for the file containing:
 *                               - observationDate: String
 *                               - observationTimestamp: Number
 *                               - ra: Number (Right Ascension)
 *                               - dec: Number (Declination)
 *                               - pixelSize: Number
 *                               - focalLength: Number
 * @param {Overscan?} overscan - Overscan object containing the overscan regions configuration
 */
var FileItem = class
{

   constructor( filePath, imageType, filter, binning, exposureTime, fileKeywords, size, matchingSizes, isCFA, isMaster, keywords, solverParams, overscan )
   {
      this.filePath = filePath;
      this.imageType = imageType;
      this.binning = binning;
      this.filter = filter;
      this.exposureTime = exposureTime;
      this.fileKeywords = fileKeywords;
      this.enabled = true;
      // real image size
      this.size = size;
      this.matchingSizes = {};
      this.matchingSizes[ BPP.GroupingMode.PRE ] = size;
      this.matchingSizes[ BPP.GroupingMode.POST ] = size;

      // Freezes the smartNamingOverride state at the time the file was added.
      // Main metadata keywords (IMAGETYP, FILTER, BINNING, EXPTIME, etc.) are overridden
      // by file path conventions only when this flag was true at add time.
      // Custom grouping keywords are always extracted from the path regardless of this flag.
      // This value may be overridden by addFile() when reconstructing from saved settings.
      this.createdWithSmartNamingEnabled = engine.smartNamingOverride;

      this.solverParams = {
         observationDate: "",
         observationTimestamp: NaN,
         ra: NaN,
         dec: NaN,
         pixelSize: NaN,
         focalLength: NaN
      };

      if ( solverParams != undefined )
      {
         let keys = Object.keys( solverParams );
         for ( let i = 0; i < keys.length; ++i )
            this.solverParams[ keys[ i ] ] = solverParams[ keys[ i ] ];
      }

      if ( matchingSizes != undefined )
      {
         let keys = Object.keys( matchingSizes );
         for ( let i = 0; i < keys.length; ++i )
            this.matchingSizes[ keys[ i ] ] = matchingSizes[ keys[ i ] ];
      }

      this.isCFA = isCFA;
      this.isMaster = isMaster;
      this.keywords = keywords
         ||
         {};

      this.overscan = new Overscan();
      if ( overscan != undefined )
         this.overscan.copyFrom( overscan );

      this.initForProcessing();
   }

   /**
    * Updates the custom grouping keywords associated to the file by extracting
    * values from the file path using smart naming conventions and from the file
    * header metadata. If a keyword exists in both sources, the file path value
    * takes precedence. Custom grouping keywords are always extracted from the
    * file path regardless of the smartNamingOverride state; this is by design,
    * as smartNamingOverride only controls the override of main metadata keywords
    * (IMAGETYP, FILTER, BINNING, EXPTIME, etc.) during file reading.
    */
   updateKeywords()
   {
      this.keywords = {};
      engine.keywords.names().forEach( keywordName =>
      {
         // get the keyword from the file path
         let value = WBPPUtils.smartNaming.getCustomKeyValueFromPath( keywordName, this.filePath );
         if ( value != undefined )
            this.keywords[ keywordName ] = WBPPUtils.smartNaming.sanitizeKeywordValue( value );
         else
         {
            // get the keyword from the file header
            value = this.fileKeywords[ keywordName ];
            if ( value != undefined )
               this.keywords[ keywordName ] = WBPPUtils.smartNaming.sanitizeKeywordValue( value );
         }
      } );
   }

   /**
    * Initializes the internal data structures for tracking file processing state.
    * Sets up default values for processed files, current state, descriptors,
    * normalization files, drizzle files and reference status.
    */
   initForProcessing()
   {
      this.processed = {};
      this.current = {};
      this.descriptor = {};
      this.localNormalizationFile = {};
      this.drizzleFile = {};
      this.isReference = {};
      this.current[ BPP.Defaults.associatedId ] = this.filePath;
      this.descriptor[ BPP.Defaults.associatedId ] = undefined;
      this.localNormalizationFile[ BPP.Defaults.associatedId ] = undefined;
      this.drizzleFile[ BPP.Defaults.associatedId ] = undefined;
      this.isReference[ BPP.Defaults.associatedId ] = false;
   }

   /**
    * Invoked when a processing step has been performed successfully.
    *
    * @param {WBPPFrameProcessingStep} step step executed
    * @param {String} filePath processed output file
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    */
   processingSucceeded( step, filePath, associatedID )
   {
      associatedID = getValidAssociatedID( associatedID );
      if ( this.processed[ associatedID ] == null )
         this.processed[ associatedID ] = {};
      this.processed[ associatedID ][ step ] = filePath;
      this.current[ associatedID ] = filePath;
   }

   /**
    * Mark the file as failed to process for the given associated ID.
    * This indicates that an error occurred during processing.
    *
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    */
   processingFailed( associatedID )
   {
      this.current[ getValidAssociatedID( associatedID ) ] = undefined;
   }

   /**
    * Checks if the file processing has failed for the given associated ID.
    *
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    * @returns {Boolean} True if processing has failed, false otherwise
    */
   failed( associatedID )
   {
      return this.current[ getValidAssociatedID( associatedID ) ] == undefined;
   }

   /**
    * Stores the associated local normalization file path for the given ID.
    * Local normalization files are used for calibrating specific images
    * in the preprocessing workflow.
    *
    * @param {String} filePath - The local normalization file path
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    */
   addLocalNormalizationFile( filePath, associatedID )
   {
      this.localNormalizationFile[ getValidAssociatedID( associatedID ) ] = filePath;
   }

   /**
    * Stores the associated drizzle file path for the given ID.
    * Drizzle files contain information for the drizzle integration process.
    *
    * @param {String} filePath - The drizzle file path
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    */
   addDrizzleFile( filePath, associatedID )
   {
      this.drizzleFile[ getValidAssociatedID( associatedID ) ] = filePath;
   }

   /**
    * Marks the file item as reference. This information tracks that the file item
    * has been used as a reference frame to align other images.
    *
    * @param {String} [associatedID=BPP.Defaults.associatedId] - The ID that identifies an associated file
    */
   markAsReference( associatedID )
   {
      this.isReference[ getValidAssociatedID( associatedID ) ] = true;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-FileItem.js - Released 2026-05-10T11:05:00Z
