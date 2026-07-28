// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-FrameGroup.js - Released 2026-05-10T11:05:00Z
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
 * Filter comparison modes for frame rejection.
 */
var FrameFilterCompareMode = {
   LESS_THAN: 0, // Frame value must be < threshold to be accepted
   GREATER_THAN: 1 // Frame value must be > threshold to be accepted
};

/**
 * Metric definitions for frame filtering/rejection.
 * Used by FrameSelection dialog to filter frames based on quality metrics.
 * Note: SNR is computed but not used for filtering (available in custom formulas).
 */
var FrameFilterMetricDefinitions = [
{
   name: "FWHM",
   key: "FWHM",
   unit: "px",
   defaultCompare: FrameFilterCompareMode.LESS_THAN, // Lower FWHM is better
   decimals: 2
},
{
   name: "Eccentricity",
   key: "eccentricity",
   unit: "",
   defaultCompare: FrameFilterCompareMode.LESS_THAN, // Lower eccentricity is better
   decimals: 3
},
{
   name: "PSF Signal Weight",
   key: "PSFSignalWeight",
   unit: "",
   defaultCompare: FrameFilterCompareMode.GREATER_THAN, // Higher weight is better
   decimals: 4
},
{
   name: "Median",
   key: "median",
   unit: "",
   defaultCompare: FrameFilterCompareMode.GREATER_THAN, // Depends on context
   decimals: 4
},
{
   name: "Stars",
   key: "numberOfStars",
   unit: "",
   defaultCompare: FrameFilterCompareMode.GREATER_THAN, // More stars is better
   decimals: 0
},
{
   name: "Custom",
   key: "custom",
   unit: "",
   defaultCompare: FrameFilterCompareMode.GREATER_THAN, // User-defined
   decimals: 4,
   isCustomFormula: true
} ];

/**
 * Available variables for custom formula expressions.
 * Maps user-friendly names to descriptor keys.
 */
var CustomFormulaVariables = [
{
   name: "FWHM",
   key: "FWHM"
},
{
   name: "Eccentricity",
   key: "eccentricity"
},
{
   name: "SNR",
   key: "SNR"
},
{
   name: "PsfSignalWeight",
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

// ----------------------------------------------------------------------------

/**
 * Represents a group of frames for batch preprocessing.
 *
 * @param {ImageType} imageType - The type of image (e.g., LIGHT, DARK, BIAS, FLAT).
 * @param {string} filter - The filter name used by flat and light frame groups.
 * @param {number} binning - The binning factor.
 * @param {number} exposureTime - The exposure time for the group.
 * @param {Object} size - The size of the frames in the group.
 * @param {boolean} isCFA - Indicates if the group is CFA (Color Filter Array).
 * @param {FileItem} firstItem - The first file item in the group.
 * @param {boolean} hasMaster - Indicates if the group has a master frame.
 * @param {Object} keywords - The keywords associated with the group.
 * @param {BPP.GroupingMode} mode - The mode of the group (e.g., PRE, POST).
 * @param {string} associatedRGBchannel - The associated RGB channel name.
 * @param {string} linkedGroupID - The ID of a linked group.
 * @param {Object} drizzleData - The drizzle data for the group.
 * @param {Object} fastIntegrationData - The fast integration data for the group.
 * @param {Object} ccData - The cosmetic correction data for the group.
 *
 * @property {ImageType} imageType - The type of image.
 * @property {string} filter - The filter name.
 * @property {number} binning - The binning factor.
 * @property {boolean} hasMaster - Indicates if the group has a master frame.
 * @property {number} exposureTime - The exposure time for the group.
 * @property {Array<number>} exposureTimes - List of all exposure times of the frames in the group.
 * @property {boolean} optimizeMasterDark - Indicates if the master dark should be optimized.
 * @property {Object} size - The size of the frames in the group.
 * @property {boolean} isCFA - Indicates if the group is CFA.
 * @property {string} CFAPattern - The CFA pattern.
 * @property {string} debayerMethod - The debayer method.
 * @property {Object} keywords - The keywords associated with the group.
 * @property {BPP.GroupingMode} mode - The mode of the group.
 * @property {Array<FileItem>} fileItems - List of frames in the group.
 * @property {string} lightOutputPedestalMode - The output pedestal mode for light frames.
 * @property {number} lightOutputPedestal - The output pedestal used for light frames.
 * @property {number} lightOutputPedestalLimit - The output pedestal limit.
 * @property {string} associatedRGBchannel - The associated RGB channel name.
 * @property {string} linkedGroupID - The ID of a linked group.
 * @property {Object} drizzleData - The drizzle data for the group.
 * @property {Object} fastIntegration - The fast integration data for the group.
 * @property {boolean} isHidden - Indicates if the group is hidden.
 * @property {boolean} isActive - Indicates if the group is active.
 * @property {number} footerLengthForCurrentHeader - The current header descriptor length.
 * @property {Object} masterFiles - The set of master file names generated for the group.
 * @property {boolean} forceNoDark - Indicates if dark frame usage is forced off.
 * @property {boolean} forceNoFlat - Indicates if flat frame usage is forced off.
 * @property {FileItem} overrideDark - The override dark frame.
 * @property {FileItem} overrideFlat - The override flat frame.
 * @property {string} id - The unique ID of the group.
 */
var FrameGroup = class
{
   constructor( imageType, filter, binning, exposureTime, size, isCFA, firstItem, hasMaster, keywords, mode, associatedRGBchannel, linkedGroupID, drizzleData, fastIntegrationData, ccData )
   {
      // commons
      this.imageType = imageType;
      this.binning = binning;
      this.hasMaster = ( imageType != ImageType.Light ) && hasMaster;

      // reference exposure time for the group
      this.exposureTime = ( imageType == ImageType.Bias ) ? 0 : exposureTime;
      // filter name of the group, used by flat and light frame groups
      this.filter = ( imageType == ImageType.Bias || imageType == ImageType.Dark ) ? "" : filter;
      // list of all exposure times of the frames in the group
      this.exposureTimes = [ this.exposureTime ];
      // used by flat and light frames to define if the master dark should be optimized
      this.optimizeMasterDark = BPP.Defaults.optimizeDarks;
      // by default the group does not have a size when created
      this.size = size
         ||
         {
            width: 0,
            height: 0
         };
      // indicates if the group is CFA (Color Filter Array)
      this.isCFA = isCFA;
      // used by light frames to define the debayer Pattern and Method
      this.CFAPattern = BPP.Defaults.cfaPattern;
      this.debayerMethod = BPP.Defaults.debayerMethod;
      // group keywords, use only the keywords enabled for the given mode
      this.keywords = engine.keywords.filterKeywordsForMode( keywords, mode );
      // the group mode
      this.mode = mode;
      // list of frames
      this.fileItems = new Array;
      // output pedestal mode for light frames
      this.lightOutputPedestalMode = BPP.Defaults.pedestalMode;
      // output pedestal used for light frames
      this.lightOutputPedestal = BPP.Defaults.lightOutputPedestal;
      // output pedestal limit
      this.lightOutputPedestalLimit = BPP.Defaults.pedestalLimit;
      // name of the RGB channel this group is associated with, used to manage the debayer option "Separate RGB channels"
      this.associatedRGBchannel = associatedRGBchannel;
      // the ID of a linked group
      this.linkedGroupID = linkedGroupID;
      // drizzle data
      this.drizzleData = {};
      // fast integration data
      this.fastIntegration = {};
      // frame selection filter configuration
      this.frameFilterConfig = null;
      // a hidden group is a group that is not visible in the control panel
      this.isHidden = false;
      // an active group is a group ready for processing
      this.isActive = true;
      // Internally stores the current header descriptor length, used to pretty print the
      // group header in diagnostic messages.
      this.footerLengthForCurrentHeader = 0;

      // MANUAL OVERRIDES

      this.forceNoDark = false;
      this.forceNoFlat = false;
      this.overrideDark = undefined;
      this.overrideFlat = undefined;

      if ( firstItem )
      {
         // we pass null from importParameters()
         this.fileItems.push( firstItem );
         this.mergeKeywords( firstItem.keywords );
         // the group takes the size of the first item
         this.size = firstItem.matchingSizes[ this.mode ];
      }

      // -------------------------------------------------------------------------
      // INITIALIZATION
      // -------------------------------------------------------------------------

      // initialize the group ID and set the defaults
      this.id = this.generateID();
      if ( drizzleData == undefined )
         this.setDrizzleDataDefaults();
      else
      {
         // we disable the linkedGroupID to avoid a resync with associated channels if drizzle data is assigned externally
         this.linkedGroupID = "";
         this.setDrizzleData( drizzleData );
         this.linkedGroupID = linkedGroupID;
      }

      // initialize the fast integration parameters
      this.setDefaultFastIntegrationData();
      this.setFastIntegrationData( fastIntegrationData );

      this.setDefaultCosmeticCorrectionData();
      this.setCcData( ccData )
   }

   /**
    * Prepares the group for being processed.
    */
   initForProcessing()
   {
      // Clear the master files set.
      this.masterFiles = {};
   }

   /**
    * Adds a new file item to the group.
    *
    * @param {FileItem} item - The file item to add.
    * @param {Boolean} ignoreCFAMatching - If true, ignores CFA matching.
    * @returns {Object} - An object indicating success or failure. On success, returns { success: true }. On failure, returns { success: false, message: string }.
    */
   appendFileItem( item, ignoreCFAMatching )
   {
      // a concrete file item cannot be added to a virtual group
      if ( this.isVirtual() )
      {
         return {
            success: false,
            message: "Attempt to add file " + item.filePath + " to the virtual group "
               + this.toString() + ", operation will be ignored."
         }
      }

      // image type and group CFA must be compatible
      if ( this.imageType == ImageType.Light && !ignoreCFAMatching && item.isCFA != this.isCFA )
      {
         return {
            success: false,
            message: "File " + item.filePath + " has a different CFA with respect "
               + "the CFA of group " + this.toString() + " so it will be discarded."
         }
      }

      // set the file item size to the group if this is the first item added
      if ( this.fileItems.length == 0 )
         this.size = item.matchingSizes[ this.mode ];

      // add the file, if this is a new master then the exposure time is set to the master exposure time
      if ( item.isMaster && !this.hasMaster )
      {

         this.fileItems.unshift( item );
         this.hasMaster = true;
         this.setExposureTime( item.exposureTime );
      }
      else
      {
         this.fileItems.push( item );
         this.addExposureTime( item.exposureTime );
      }

      // switch to fast integration if fast mode has not yet enabled or disabled manually, when we have more than 500 frames
      if ( engine.autoIntegrationMode
         && this.mode == BPP.GroupingMode.POST
         && this.imageType == ImageType.Light
         && this.fileItems.length >= BPP.Defaults.autoFastIntegrationThreshold
         && this.fastIntegrationData.manuallyChanged == false )
      {
         this.enableFastIntegration( true, /*manuallyChanged*/ true );
         engine.automaticFIgroups.push( this );
      }

      return {
         success: true
      }
   }

   /**
    * This is a convenient method to clone an existing group keeping only the
    * given active items. Caller must ensure that active items are items of the
    * group otherwise an unexpected behavior.
    *
    * @param {Array<ActiveFrame>} activeItems - The active items to include in the cloned group.
    * @returns {FrameGroup} - The cloned FrameGroup with the specified active items.
    */
   cloneWithActiveItems( activeItems )
   {
      let frameGroup = new FrameGroup(
         this.imageType,
         this.filter,
         this.binning,
         this.exposureTime,
         this.size,
         this.isCFA,
         undefined,
         this.hasMaster,
         this.keywords,
         this.mode,
         this.associatedRGBchannel,
         this.linkedGroupID,
         this.drizzleData,
         this.fastIntegrationData,
         this.ccData );
      frameGroup.fileItems = activeItems.map( item => item.fileItem );
      return frameGroup;
   }

   /**
    * Returns true if the group is virtual. A virtual group is a group that is programmatically
    * created to support the accomplishment of one or more tasks but does not correspond to
    * any concrete group that is created when file items are added to BPP. An example is the
    * _R, _G, and _B groups that refer to the separated RGB channels associated with a CFA group: these
    * groups are created programmatically in the groups list when CFA groups get debayered and the user
    * enables the Separate RGB Channel debayer feature.
    *
    * @returns {boolean} true if the group is virtual
    */
   isVirtual()
   {
      return this.associatedRGBchannel != null;
   }

   /**
    * Checks if drizzle is available for the frame group.
    *
    * Drizzle is a technique used in image processing to improve the resolution
    * of images by combining multiple exposures. This function checks if the
    * necessary conditions are met for drizzle to be applied to this frame group.
    *
    * @returns {boolean} True if drizzle is available, false otherwise.
    */
   isDrizzleAvailable()
   {
      // disabled for all virtual groups that are not one of the RBG associated channels
      if ( this.isVirtual() && !( this.associatedRGBchannel == BPP.AssociatedChannel.R || this.associatedRGBchannel == BPP.AssociatedChannel.G || this.associatedRGBchannel == BPP.AssociatedChannel.B ) )
         return false;

      // superpixel debayer is not compatible, so if the group is CFA and debayer mode is superpixel we disable drizzle
      if ( this.isCFA )
      {
         // we need to search the calibration group of all frames and ensure that no superpixel is selected as debayer mode
         let calibrationGroups = engine.groupsManager.groupsForMode( BPP.GroupingMode.PRE );
         let superpixelFrames = {};
         for ( let i = 0; i < calibrationGroups.length; ++i )
         {
            let cg = calibrationGroups[ i ];
            if ( cg.imageType == ImageType.Light && cg.isCFA && cg.debayerMethod == Debayer.SuperPixel )
            {
               for ( let j = 0; j < cg.fileItems.length; ++j )
                  superpixelFrames[ cg.fileItems[ j ].filePath ] = true;
            }
         }

         // now check if the group contains at least one frame debayered with superpixel
         for ( let i = 0; i < this.fileItems.length; ++i )
         {
            if ( !!superpixelFrames[ this.fileItems[ i ].filePath ] )
            {
               return false;
            }
         }
      }

      return true;
   }

   /**
    * Checks if drizzle is enabled for the frame group.
    *
    * @returns {boolean} True if drizzle is enabled, false otherwise.
    */
   isDrizzleEnabled()
   {
      if ( this.drizzleData.enabled == undefined )
         return false;
      return this.drizzleData.enabled && this.isDrizzleAvailable();
   }

   /**
    * Enables drizzle for the frame group.
    */
   enableDrizzle()
   {
      // drizzle can be enabled only if available
      this.drizzleData.enabled = this.isDrizzleAvailable();
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Disables drizzle for the frame group.
    */
   disableDrizzle()
   {
      this.drizzleData.enabled = false;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Sets the drizzle data for the frame group.
    *
    * @param {Object} data The drizzle data to set.
    */
   setDrizzleData( data )
   {
      // we don't set any drizzle data on associated channels (drizzle is not applicable)
      if ( data == undefined || !this.isDrizzleAvailable() ) return;

      if ( data.enabled )
         this.enableDrizzle()
      else
         this.disableDrizzle();
      if ( data.fast != undefined )
         this.setDrizzleFast( data.fast );
      if ( data.scale != undefined )
         this.setDrizzleScale( data.scale );
      if ( data.dropShrink != undefined )
         this.setDrizzleDropShrink( data.dropShrink );
      if ( data.function != undefined )
         this.setDrizzleFunction( data.function );
      if ( data.gridSize != undefined )
         this.setDrizzleGridSize( data.gridSize );
   }

   /**
    * Sets the default values for the drizzle data of the frame group.
    *
    * This function initializes the drizzle data with default values. It sets the
    * drizzle enabled status based on whether drizzle is available for the frame group.
    * Other drizzle parameters such as fast mode, scale, drop shrink, function, and grid size
    * are set to their respective default values.
    */
   setDrizzleDataDefaults()
   {
      this.drizzleData.enabled = this.isDrizzleEnabled();
      this.setDrizzleFast( BPP.Defaults.drizzleFast );
      this.setDrizzleScale( BPP.Defaults.drizzleScale );
      if ( this.isCFA )
         this.setDrizzleDropShrink( BPP.Defaults.drizzleDropShrinkCfa );
      else
         this.setDrizzleDropShrink( BPP.Defaults.drizzleDropShrinkMono );
      this.setDrizzleFunction( BPP.Defaults.drizzleFunction );
      this.setDrizzleGridSize( BPP.Defaults.drizzleGridSize );
   }

   /**
    * Synchronizes the drizzle settings on associated RGB channels.
    *
    * This function ensures that the drizzle settings (enabled status, fast mode, scale, etc.)
    * are consistent across all associated RGB channels (R, G, B) within the same linked group.
    * This is necessary to ensure that the R, G, and B channels can be combined correctly
    * during the drizzle integration process.
    *
    * @param {string} linkedGroupID The ID of the linked group.
    * @param {Object} drizzleData The drizzle data to synchronize.
    */
   syncDrizzleOnAssociatedRGBChannels( linkedGroupID, drizzleData )
   {
      if ( linkedGroupID == undefined )
         return;

      // we keep the drizzle scale in sync to ensure that R, G and B channels can be combined
      let groups = engine.groupsManager.groupsForMode( BPP.GroupingMode.POST )
         .filter( g => g.linkedGroupID == linkedGroupID )
         .filter( g => ( g.associatedRGBchannel == BPP.AssociatedChannel.R
            || g.associatedRGBchannel == BPP.AssociatedChannel.G
            || g.associatedRGBchannel == BPP.AssociatedChannel.B ) );

      for ( let i = 0; i < groups.length; ++i )
      {
         groups[ i ].drizzleData.enabled = drizzleData.enabled;
         groups[ i ].drizzleData.fast = drizzleData.fast;
         groups[ i ].drizzleData.scale = drizzleData.scale;
         groups[ i ].drizzleData.dropShrink = drizzleData.dropShrink;
         groups[ i ].drizzleData.function = drizzleData.function;
         groups[ i ].drizzleData.gridSize = drizzleData.gridSize;
      }
   }

   /**
    * Sets the fast mode for drizzle integration.
    *
    * Fast mode uses Look Up Tables (LUTs) to compute the overlapping areas of each drizzle droplet,
    * significantly increasing the execution speed at the price of negligible error in the calculation
    * of droplet overlapping areas. This option is generally recommended.
    *
    * @param {boolean} fast - True to enable fast mode, false to disable it.
    */
   setDrizzleFast( fast )
   {
      this.drizzleData.fast = fast;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Sets the scale factor for drizzle integration.
    *
    * The scale factor determines the resolution of the output image relative to the input images.
    * For example, a scale factor of 2 will produce an output image with twice the resolution of the input images.
    *
    * @param {number} scale - The scale factor to set.
    */
   setDrizzleScale( scale )
   {
      this.drizzleData.scale = scale;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Sets the drop shrink factor for drizzle integration.
    *
    * The drop shrink factor is a reduction factor applied to input image pixels (drops).
    * Smaller input pixels tend to yield sharper results because the integrated image is
    * formed by convolution with a smaller PSF (Point Spread Function). However, smaller
    * input pixels are more prone to dry (uncovered) output pixels, visible patterns caused
    * by partial sampling, and overall decreased SNR (Signal-to-Noise Ratio). Low shrink
    * factors require more and better dithered input images.
    *
    * @param {number} dropShrink - The drop shrink factor to set.
    */
   setDrizzleDropShrink( dropShrink )
   {
      this.drizzleData.dropShrink = dropShrink;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Sets the drizzle kernel function for drizzle integration.
    *
    * The kernel function determines the shape of the drizzle droplets. Different kernel functions
    * can be used to achieve different effects in the integrated image. For example, a Gaussian kernel
    * can be used to achieve a smoother result, while a square kernel can be used to preserve sharp edges.
    *
    * @param {number} f - The kernel function to set.
    */
   setDrizzleFunction( f )
   {
      this.drizzleData.function = f;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Sets the grid size for drizzle integration.
    *
    * The grid size parameter defines the number of discrete function values computed to approximate
    * the double integral of the kernel surface function. More function evaluations improve the accuracy
    * of numerical integration at the cost of more computational work. This parameter is relevant when
    * Gaussian and variable shape drizzle kernel functions are used.
    *
    * @param {number} gridSize - The grid size to set.
    */
   setDrizzleGridSize( gridSize )
   {
      this.drizzleData.gridSize = gridSize;
      this.syncDrizzleOnAssociatedRGBChannels( this.linkedGroupID, this.drizzleData );
   }

   /**
    * Gets the name of the drizzle kernel function.
    *
    * This function returns the name of the drizzle kernel function based on the current
    * drizzle settings. The kernel function determines the shape of the drizzle droplets.
    *
    * @returns {string} The name of the drizzle kernel function.
    */
   getDrizzleFunctionName()
   {
      let kernels = [
         "Square",
         "Circular",
         "Gaussian",
         "VarShape, \u03b2 = 1",
         "VarShape, \u03b2 = 1.5",
         "VarShape, \u03b2 = 3",
         "VarShape, \u03b2 = 4",
         "VarShape, \u03b2 = 5",
         "VarShape, \u03b2 = 6"
      ];

      return this.isDrizzleEnabled() ? kernels[ this.drizzleFunction() ] : "";
   }

   /**
    * Gets the drizzle grid size as a string.
    *
    * This function returns the grid size used for drizzle integration as a string.
    * The grid size is relevant when Gaussian and variable shape drizzle kernel functions are used.
    * If the kernel function is not Gaussian or variable shape, an empty string is returned.
    *
    * @returns {string} The grid size as a string, or an empty string if not applicable.
    */
   getDrizzleGridSizeString()
   {
      if ( this.drizzleFunction() < DrizzleIntegration.Kernel_Gaussian )
         return "";
      return "grid = " + this.drizzleData.gridSize;
   }

   /**
    * Gets the fast mode status for drizzle integration.
    *
    * Fast mode uses Look Up Tables (LUTs) to compute the overlapping areas of each drizzle droplet,
    * significantly increasing the execution speed at the price of negligible error in the calculation
    * of droplet overlapping areas. This option is generally recommended.
    *
    * @returns {boolean} True if fast mode is enabled, false otherwise.
    */
   drizzleFast()
   {
      if ( this.drizzleData != undefined && this.drizzleData.fast != undefined )
         return this.drizzleData.fast;
      return BPP.Defaults.drizzleFast; // default
   }

   /**
    * Gets the scale factor for drizzle integration.
    *
    * The scale factor determines the resolution of the output image relative to the input images.
    * For example, a scale factor of 2 will produce an output image with twice the resolution of the input images.
    *
    * @returns {number} The scale factor for drizzle integration.
    */
   drizzleScale()
   {
      if ( this.drizzleData != undefined && this.drizzleData.scale != undefined )
         return this.drizzleData.scale;
      return BPP.Defaults.drizzleScale; // default
   }

   /**
    * Gets the drop shrink factor for drizzle integration.
    *
    * The drop shrink factor is a reduction factor applied to input image pixels (drops).
    * Smaller input pixels tend to yield sharper results because the integrated image is
    * formed by convolution with a smaller PSF (Point Spread Function). However, smaller
    * input pixels are more prone to dry (uncovered) output pixels, visible patterns caused
    * by partial sampling, and overall decreased SNR (Signal-to-Noise Ratio). Low shrink
    * factors require more and better dithered input images.
    *
    * @returns {number} The drop shrink factor for drizzle integration.
    */
   drizzleDropShrink()
   {
      if ( this.drizzleData != undefined && this.drizzleData.dropShrink != undefined )
         return this.drizzleData.dropShrink;
      return this.isCFA ? BPP.Defaults.drizzleDropShrinkCfa : BPP.Defaults.drizzleDropShrinkMono; // default
   }

   /**
    * Gets the drizzle kernel function.
    *
    * The kernel function determines the shape of the drizzle droplets. Different kernel functions
    * can be used to achieve different effects in the integrated image. For example, a Gaussian kernel
    * can be used to achieve a smoother result, while a square kernel can be used to preserve sharp edges.
    *
    * @returns {number} The drizzle kernel function.
    */
   drizzleFunction()
   {
      if ( this.drizzleData != undefined && this.drizzleData.function != undefined )
         return this.drizzleData.function;
      return BPP.Defaults.drizzleFunction; // default
   }

   /**
    * Gets the grid size for drizzle integration.
    *
    * The grid size parameter defines the number of discrete function values computed to approximate
    * the double integral of the kernel surface function. More function evaluations improve the accuracy
    * of numerical integration at the cost of more computational work. This parameter is relevant when
    * Gaussian and variable shape drizzle kernel functions are used.
    *
    * @returns {number} The grid size for drizzle integration.
    */
   drizzleGridSize()
   {
      if ( this.drizzleData != undefined && this.drizzleData.gridSize != undefined )
         return this.drizzleData.gridSize;
      return BPP.Defaults.drizzleGridSize; // default
   }

   /**
    * Gets the estimated size of a drizzled frame.
    *
    * This function calculates the size of a drizzled frame based on the original frame size
    * and the drizzle scale factor. The size is determined by multiplying the original frame size
    * by the square of the drizzle scale factor.
    *
    * @returns {number} The estimated size of a drizzled frame.
    */
   drizzledFrameSize()
   {
      return this.frameSize() * this.drizzleScale() * this.drizzleScale();
   }

   /**
    * Stores the master file name for the group given the master type and the variant.
    *
    * This function associates a master file name with the frame group based on the specified
    * master type and variant. The master type can be LIGHT, DRIZZLE, or RECOMBINED, and the
    * variant can be REGULAR or CROPPED. This information is used to keep track of different
    * versions of master files generated during the preprocessing steps.
    *
    * @param {string} name - The name of the master file to associate.
    * @param {BPP.MasterType} type - The type of master file, can be LIGHT, DRIZZLE, or RECOMBINED.
    * @param {BPP.MasterVariant} variant - The master variant, can be REGULAR or CROPPED.
    */
   setMasterFileName( name, type, variant )
   {
      if ( type == undefined )
         type = BPP.MasterType.MASTER_LIGHT;
      if ( variant == undefined )
         variant = BPP.MasterVariant.REGULAR;

      this.masterFiles[ type + "_" + variant ] = name;
   }

   /**
    * Returns the master file name associated with the given type and variant.
    *
    * This function retrieves the master file name for the frame group based on the specified
    * master type and variant. The master type can be LIGHT, DRIZZLE, or RECOMBINED, and the
    * variant can be REGULAR or CROPPED. For bias and dark frames, the file path of the first
    * file item is returned as they do not have types and variants.
    *
    * @param {BPP.MasterType} type - The type of master file, can be LIGHT, DRIZZLE, or RECOMBINED.
    * @param {BPP.MasterVariant} variant - The master variant, can be REGULAR or CROPPED.
    * @returns {string|undefined} The master file name if found, otherwise undefined.
    */
   getMasterFileName( type, variant )
   {
      // bias and darks do not have types and variants
      if ( this.imageType == ImageType.Bias || this.imageType == ImageType.Dark )
         return this.fileItems[ 0 ].filePath;

      if ( type == undefined )
         type = BPP.MasterType.MASTER_LIGHT;
      if ( variant == undefined )
         variant = BPP.MasterVariant.REGULAR;
      if ( this.masterFiles.hasOwnProperty( type + "_" + variant ) )
         return this.masterFiles[ type + "_" + variant ];
      else
         return undefined;
   }

   /**
    * Checks if the frame group has overscan information.
    *
    * This function determines whether the frame group contains valid overscan information.
    * Overscan information includes the enabled status and the presence of defined overscan regions.
    *
    * @returns {boolean} True if the frame group has overscan information, false otherwise.
    */
   hasOverscanInfo()
   {
      return this.hasMaster && this.fileItems[ 0 ].overscan.enabled && this.fileItems[ 0 ].overscan.hasOverscanRegions();
   }

   /**
    * Gets the overscan description for the frame group.
    *
    * This function returns a string representation of the overscan settings for the frame group.
    * If the frame group has a master file, the overscan information from the first file item is used.
    *
    * @returns {string} The overscan description if available, otherwise an empty string.
    */
   getOverscanDescription()
   {
      if ( this.hasMaster )
         return this.fileItems[ 0 ].overscan.toString();
      return "";
   }

   /**
    * Gets the overscan information for the frame group.
    *
    * This function returns the overscan information for the frame group if it has a master file.
    * The overscan information is retrieved from the first file item in the frame group.
    *
    * @returns {Object|undefined} The overscan information if available, otherwise undefined.
    */
   getOverscanInfo()
   {
      if ( this.hasMaster )
         return this.fileItems[ 0 ].overscan;
      return undefined;
   }

   /**
    * Sets the default values for the fast integration data of the frame group.
    *
    * This function initializes the fast integration data with default values. It sets the
    * fast integration enabled status based on the engine's fast mode setting. Other fast
    * integration parameters such as manually changed status, save registered images, and
    * weighting scheme are set to their respective default values.
    */
   setDefaultFastIntegrationData()
   {
      this.fastIntegrationData = {
         enabled: engine.fastMode,
         manuallyChanged: false,
         saveRegisteredImages: false,
         weightingScheme: BPP.FastIntegrationWeightScheme.NONE
      };
   }

   /**
    * Enables or disables fast integration for the frame group.
    *
    * Fast integration is an in-memory process that reads, aligns, normalizes, and integrates images
    * to generate a master light without the need of writing intermediate results as disk files.
    *
    * @param {boolean} value - True to enable fast integration, false to disable it.
    * @param {boolean} manuallyChanged - True if the change was made manually, false otherwise.
    */
   enableFastIntegration( value, manuallyChanged = false )
   {
      this.fastIntegrationData.enabled = value != undefined ? value : engine.fastMode;
      this.fastIntegrationData.manuallyChanged = manuallyChanged;
   }

   /**
    * Enables or disables the saving of registered images during fast integration.
    *
    * When enabled, the registered images are saved to disk for further inspection if required.
    *
    * @param {boolean} value - True to enable saving of registered images, false to disable it.
    */
   enableFastIntegrationImageSaving( value )
   {
      this.fastIntegrationData.saveRegisteredImages = value != undefined ? value : false;
   }

   /**
    * Sets the weighting scheme for fast integration.
    *
    * The weighting scheme determines how the images are weighted during the integration process.
    *
    * @param {number} value - The weighting scheme to set.
    */
   enableFastIntegrationWeightingScheme( value )
   {
      this.fastIntegrationData.weightingScheme = value != undefined ? value : BPP.FastIntegrationWeightScheme.NONE;
   }

   /**
    * Checks if saving registered images during fast integration is enabled.
    *
    * This function returns a boolean indicating whether the saving of registered images
    * during fast integration is enabled. When enabled, the registered images are saved
    * to disk for further inspection if required.
    *
    * @returns {boolean} True if saving registered images is enabled, false otherwise.
    */
   fastIntegrationSaveImageEnabled()
   {
      return this.fastIntegrationData.saveRegisteredImages;
   }

   /**
    * Sets the fast integration data for the frame group.
    *
    * This function initializes the fast integration data with the provided values. If any value is not provided,
    * it retains its current value.
    *
    * @param {Object} data - The fast integration data to set.
    */
   setFastIntegrationData( data )
   {
      if ( data != undefined )
         if ( data.enabled != undefined )
         {
            let keys = Object.keys( data );
            for ( let i = 0; i < keys.length; ++i )
            {
               let key = keys[ i ];
               this.fastIntegrationData[ key ] = data[ key ];
            }
         }
   }

   /**
    * Sets the default values for the cosmetic correction data of the frame group.
    *
    * This function initializes the cosmetic correction data with default values. It sets the
    * cosmetic correction enabled status, high sigma value, and the template icon name.
    */
   setDefaultCosmeticCorrectionData()
   {
      this.ccData = {
         enabled: BPP.Defaults.ccEnabled,
         highSigma: BPP.Defaults.ccHighSigma,
         CCTemplate: ""
      }
   }

   /**
    * Enables or disables cosmetic correction for the frame group.
    *
    * @param {boolean} value - True to enable cosmetic correction, false to disable it.
    */
   enableCC( value )
   {
      this.ccData.enabled = value != undefined ? value : BPP.Defaults.ccEnabled;
      if ( this.ccData.enabled )
         this.ccData.CCTemplate = "";
   }

   /**
    * Sets the high sigma value for cosmetic correction.
    *
    * @param {number} value - The high sigma value to set.
    */
   setCcHighSigma( value )
   {
      this.ccData.highSigma = value != undefined ? value : BPP.Defaults.ccHighSigma;
   }

   /**
    * Sets the template icon name for cosmetic correction.
    *
    * @param {string} name - The name of the template icon to set.
    */
   setCcTemplate( name )
   {
      this.ccData.CCTemplate = name;
      if ( name != "" && name != undefined )
         this.ccData.enabled = false;
   }

   /**
    * Sets the cosmetic correction data for the frame group.
    *
    * This function initializes the cosmetic correction data with the provided values. If any value is not provided,
    * it retains its current value.
    *
    * @param {Object} data - The cosmetic correction data to set.
    */
   setCcData( data )
   {
      if ( data != undefined )
         if ( data.enabled != undefined )
         {
            let keys = Object.keys( data );
            for ( let i = 0; i < keys.length; ++i )
            {
               let key = keys[ i ];
               this.ccData[ key ] = data[ key ];
            }
         }
   }

   /**
    * Validates the cosmetic correction settings for the frame group.
    *
    * This function checks the following:
    * 1. If cosmetic correction is enabled, then the master dark duration is compatible (exposure difference is less than 30 seconds).
    * 2. If cosmetic correction is enabled, a master dark must be present (returns an error message if missing).
    *
    * @param {Object} masterDark - The master dark frame to validate against.
    * @returns {string|null} An error message if validation fails, otherwise null.
    */
   validateCC( masterDark )
   {
      if ( !this.ccData.enabled )
         return null;
      if ( !masterDark )
         return "Cosmetic Correction requires a master dark";
      let exposureDiff = Math.abs( masterDark.exposureTime - this.exposureTime );
      if ( exposureDiff > BPP.Defaults.ccMaxDarkExposureDiff )
      {
         return format( "Master dark has an exposure time difference of %.2f, Cosmetic Correction may lead to inaccurate results", exposureDiff );
      }
      return null;
   }

   /**
    * Compute the total integration time for the group.
    *
    * @param {Boolean} onlyActiveFrames - True if total time takes into account only active frames.
    * @returns {number} Total exposure time in seconds.
    */
   totalExposureTime( onlyActiveFrames )
   {
      return ( onlyActiveFrames ? this.activeFrames() : this.fileItems ).reduce( ( acc, fileItem ) => ( acc + fileItem.exposureTime ), 0 );
   }

   /**
    * Merge the keywords object into the group's keywords object filtering only
    * the keywords enabled for the group's mode.
    *
    * @param {{String:String}} keywords - The keywords key-value map.
    */
   mergeKeywords( keywords )
   {
      Object.keys( keywords ).forEach( k =>
      {
         this.keywords[ k ] = keywords[ k ];
      } );
      this.keywords = engine.keywords.filterKeywordsForMode( this.keywords, this.mode );
   }

   /**
    * Returns the group size string.
    *
    * @return {*} "width"x"height" string
    */
   sizeString()
   {
      return this.size.width + "x" + this.size.height;
   }

   /**
    * Generates a unique ID for the frame group.
    *
    * This function creates a unique identifier for the frame group based on its properties.
    * The ID is generated by concatenating the image type, filter, binning, exposure time, and size.
    *
    * @returns {string} The generated unique ID.
    */
   generateID()
   {
      // WBPP 2.0.2 - do not change!
      let pre_id_items = [
         this.imageType,
         this.binning,
         this.filter,
         this.exposureTime,
         this.colorSpaceToString()
      ];

      // WBPP 2.1 and above
      // NB: **** migration to be update in case of changes! ****
      let post_id_items = [
         this.mode
      ];

      // WBPP 2.2.0
      post_id_items.push( this.associatedRGBchannel || "none" );

      // WBPP 2.4.2
      post_id_items.push( this.sizeString() );

      let ID = pre_id_items.join( "_" )
      ID = ID + "_" + Object.keys( this.keywords ).map( k => k + ":" + this.keywords[ k ] ).join( "_" );
      ID = ID + "_" + post_id_items.join( "_" )

      return ID;
   }

   /**
    * Gets the list of active frames in the frame group.
    *
    * Active frames are those that are not marked as disabled. This function filters
    * the file items in the frame group and returns only the active ones.
    *
    * @returns {Array} The list of active frames.
    */
   activeFrames( associatedID )
   {
      // returns the frames that have been processes successfully, taking into account the
      // associated id to the separated RGB groups, if set to the group or if provided directly
      let id = getValidAssociatedID( associatedID );
      if ( this.isVirtual() )
         id = this.associatedRGBchannel;
      return this.fileItems.filter( item => !item.failed( id ) ).map( item =>
      {
         return new ActiveFrame( item, id );
      } );
   }

   /**
    * Checks if the frame group has the same parameters as the provided parameters.
    *
    * This function compares the frame group's parameters with the provided parameters
    * to determine if they are the same. The parameters compared include image type,
    * filter, binning, exposure time, size, and whether the group is CFA. Tolerances
    * for exposure time and light exposure time are also considered.
    *
    * @param {string} imageType - The image type to compare.
    * @param {string} filter - The filter to compare.
    * @param {number} binning - The binning to compare.
    * @param {number} exposureTime - The exposure time to compare.
    * @param {Object} size - The size to compare.
    * @param {boolean} isCFA - Whether the group is CFA to compare.
    * @param {number} tolerance - The tolerance for exposure time comparison.
    * @param {number} lightExposureTolerance - The tolerance for light exposure time comparison.
    * @param {string} mode - The mode to compare.
    * @returns {boolean} True if the parameters are the same, false otherwise.
    */
   sameParameters( imageType, filter, binning, exposureTime, size, isCFA, exposureTolerance, lightExposureTolerance, mode )
   {
      if ( this.imageType != imageType || this.binning != binning || this.mode != mode )
         return false;

      // if group has a size and a size is provided then they must match
      if ( this.size.width != size.width )
         return false;
      if ( this.size.height != size.height )
         return false;

      switch ( imageType )
      {
         case ImageType.Bias:
            return true
         case ImageType.Dark:
            return ( Math.abs( this.exposureTime - exposureTime ) <= Math.max( BPP.Constants.MIN_EXPOSURE_TOLERANCE, exposureTolerance ) );
         case ImageType.Flat:
         case ImageType.Unknown:
            return this.filter == filter;
         case ImageType.Light:
            return this.isCFA == isCFA && this.filter == filter && Math.abs( this.exposureTime - exposureTime ) <= lightExposureTolerance;
      }
      return false;
   }

   /**
    * Returns the number of matches between the values of the current group keywords and
    * the values of the keywords object provided. If a mismatch occurs (values are different),
    * then -1 is returned otherwise the count of the matches is returned.
    * If strictDirectMatching is true, then return -1 if the group contains a keyword that is not in the
    * provided keywords. If strictInverseMatching is true, then return -1 if the provided keywords contain
    * a keyword that is not in the group.
    *
    * @param {{String:String}} keywords - The keywords key-value map.
    * @param {boolean} strictDirectMatching - Skip a group if it has a keyword that is not provided.
    * @param {boolean} strictInverseMatching - Skip a group if it does not have a value for a given keyword.
    * @returns {number} The number of matching keywords, or -1 if a mismatch occurs.
    */
   keywordsMatchCount( keywords, strictDirectMatching, strictInverseMatching )
   {
      // scan the list of group's keywords and count the number of keywords
      let keys = Object.keys( this.keywords );
      let count = 0;
      for ( let i = 0; i < keys.length; ++i )
      {
         let key = keys[ i ];
         if ( keywords[ key ] )
         {
            if ( this.keywords[ key ] == keywords[ key ] )
               count++;
            else
               return -1;
         }
         else if ( strictDirectMatching )
         {
            // the group contains a keyword that is not in the provided keywords, in this case
            // the group does not strict match
            return -1;
         }
      }

      if ( strictInverseMatching )
      {
         // do the inverse check i.e. check if the list of provided keywords contains a keyword
         // that is not in the group, ni that case the group is not strictly matching
         let kw = Object.keys( keywords );
         for ( let i = 0; i < kw.length; ++i )
            if ( !this.keywords[ kw[ i ] ] )
               return -1;
      }
      return count;
   }

   /**
    * Removes a file item at the specified index.
    *
    * This function removes the file item at the given index from the frame group.
    * If the new top element in the file items list is a master, the group is updated accordingly.
    * If the file items list becomes empty, the group's master status is set to false.
    *
    * @param {number} i - The index of the file item to remove.
    */
   removeItem( i )
   {
      this.fileItems.splice( i, 1 );
      // if the new on-top element is a master then update the group accordingly
      if ( this.fileItems.length > 0 )
      {
         if ( this.fileItems[ 0 ] )
            this.hasMaster = this.fileItems[ 0 ].isMaster;
      }
      else
      {
         this.hasMaster = false;
      }
   }

   /**
    * Checks if the provided rejection type is good for the group.
    *
    * This function evaluates whether the specified pixel rejection algorithm is suitable
    * for the frame group. It considers the number of frames in the group and the type of
    * rejection algorithm. If the rejection algorithm is not appropriate, it returns a
    * reason for the rejection.
    *
    * @param {number} rejection - The pixel rejection algorithm to evaluate.
    * @returns {[boolean, string]} An array where the first element is a boolean indicating
    * whether the rejection algorithm is good, and the second element is a string with the reason if not.
    */
   rejectionIsGood( rejection )
   {
      if ( rejection == BPP.REJECTION_AUTO )
         return [ true, "" ];

      // Invariants
      switch ( rejection )
      {
         case ImageIntegration.NoRejection:
            return [ false, "No pixel rejection algorithm has been selected" ];
         case ImageIntegration.MinMax:
            return [ false, "Min/Max rejection should not be used for production work" ];
         case ImageIntegration.CCDClip:
            return [ false, "CCD clipping rejection has been deprecated" ];
         default:
            break;
      }
      let selectedRejection = ( rejection !== BPP.REJECTION_AUTO ) ? rejection : this.bestRejectionMethod();

      // Selections dependent on the number of frames
      let n = this.fileItems.length;
      switch ( selectedRejection )
      {
         case ImageIntegration.PercentileClip:
            if ( n > 8 )
               return [ false, "Percentile clipping should only be used for small sets of eight or less images" ];
            break;
         case ImageIntegration.SigmaClip:
            if ( n < 8 )
               return [ false, "Sigma clipping requires at least 8 images to provide minimally reliable results; consider using percentile clipping" ];
            if ( n > 15 )
               return [ false, "Winsorized sigma clipping will work better than sigma clipping for sets of 15 or more images" ];
            break;
         case ImageIntegration.WinsorizedSigmaClip:
            if ( n < 8 )
               return [ false, "Winsorized sigma clipping requires at least 8 images to provide minimally reliable results; consider using percentile clipping" ];
            break;
         case ImageIntegration.AveragedSigmaClip:
            if ( n < 8 )
               return [ false, "Averaged sigma clipping requires at least 8 images to provide minimally reliable results; consider using percentile clipping for less than 8 frames" ];
            if ( n > 10 )
               return [ false, "Sigma clipping or Winsorized sigma clipping will work better than averaged sigma clipping for sets of 10 or more images" ];
            break;
         case ImageIntegration.LinearFit:
            if ( n < 8 )
               return [ false, "Linear fit clipping requires at least 15 images to provide reliable results; consider using percentile clipping for less than 8 frames" ];
            if ( n < 20 )
               return [ false, "Linear fit clipping may not be better than Winsorized sigma clipping for sets of less than 15-20 images" ];
            break;
         case ImageIntegration.Rejection_ESD:
            if ( n < 8 )
               return [ false, "ESD requires at least 15 images to provide reliable results; consider using percentile clipping for less than 8 frames" ];
            if ( n < 20 )
               return [ false, "ESD may not be better than Winsorized sigma clipping for sets of less than 20 images" ];
            if ( n < 25 )
               return [ false, "ESD may not be better than linear fit clipping for sets of less than 20-25 images" ];
            break;
         case ImageIntegration.Rejection_RCR:
            if ( n < 15 )
               return [ false, "RCR requires at least 15 images to provide reliable results; consider using percentile clipping for less than 8 frames" ];
            break;
         default: // ?!
            break;
      }

      return [ true, "" ];
   }

   /**
    * Returns the best rejection method for the group.
    *
    * This function determines the most suitable pixel rejection algorithm based on the
    * current number of active frames in the group. The selection is made considering
    * the type of images and the number of frames to ensure optimal integration results.
    *
    * @returns {number} The best rejection method.
    */
   bestRejectionMethod()
   {
      let n = this.activeFrames().length;
      if ( n < 6 )
         return ImageIntegration.PercentileClip;
      if ( n <= 15 || this.imageType == ImageType.Bias || this.imageType == ImageType.Dark )
         return ImageIntegration.WinsorizedSigmaClip;
      return ImageIntegration.LinearFit;
   }

   /**
    * Adds a new exposure time and updates the exposure data accordingly.
    *
    * This function adds a new exposure time to the list of exposure times for the group.
    * It checks if the exposure time is already present within a tolerance and updates
    * the list of exposure times if it is not.
    *
    * @param {number} time - The exposure time to add.
    */
   addExposureTime( time )
   {
      // check exposure with tolerance
      let hasExposure = false;
      for ( let i = 0; i < this.exposureTimes.length; ++i )
      {
         if ( Math.abs( time - this.exposureTimes[ i ] ) < BPP.Constants.MIN_EXPOSURE_TOLERANCE )
         {
            hasExposure = true;
            break;
         }
      }
      if ( !hasExposure )
      {
         this.exposureTimes.push( time );
         this.exposureTimes.sort( ( a, b ) => a - b )
      }
   }

   /**
    * Assigns the nominal exposure time of the group.
    *
    * This function sets the nominal exposure time for the group and updates the list
    * of exposure times to include only the specified time. For bias frames, the exposure
    * time is always set to zero.
    *
    * @param {number} time - The nominal exposure time to set.
    */
   setExposureTime( time )
   {
      let sanitizedValue = ( this.imageType != ImageType.Bias ) ? time : 0;
      this.exposureTimes = [ sanitizedValue ];
      this.exposureTime = sanitizedValue;
   }

   /**
    * Converts the exposure time to a string representation.
    *
    * This function returns a string representation of the exposure time for the group.
    * The exposure time is formatted in seconds with a precision of two decimal places.
    *
    * @returns {string} The exposure time as a string.
    */
   exposureToString()
   {
      return format( "%.2fs", this.exposureTime );
   }

   /**
    * Converts the exposure times to a string representation.
    *
    * This function returns a string representation of the list of exposure times for the group.
    * Each exposure time is formatted in seconds with a precision of two decimal places.
    *
    * @returns {string} The exposure times as a string.
    */
   exposureTimesToString()
   {
      if ( this.exposureTimes.length > 1 )
         return '[' + this.exposureTimes.map( exposure => format( "%.2fs", exposure ) ).join( ', ' ) + ']';
      return this.exposureToString();
   }

   /**
    * Converts the exposure times to an extended string representation.
    *
    * This function returns an extended string representation of the list of exposure times for the group.
    * Each exposure time is formatted in seconds with a precision of two decimal places, and the list is
    * enclosed in square brackets.
    *
    * @returns {string} The extended exposure times as a string.
    */
   exposureTimesToExtendedString()
   {
      if ( this.exposureTimes.length > 1 )
         return format( "%.2fs", this.exposureTimes[ this.exposureTimes.length - 1 ] )
            + ' - [' + this.exposureTimes.map( ( exposure ) => format( "%.2fs", exposure ) ).join( ', ' ) + ']';
      return format( "%.2fs", this.exposureTime );
   }

   /**
    * Converts the minimum and maximum exposure times to a string representation.
    *
    * This function returns a string representation of the minimum and maximum exposure times
    * for the group. The exposure times are formatted in seconds with a precision of two decimal places,
    * and the range is represented as "min - max".
    *
    * @returns {string} The minimum and maximum exposure times as a string.
    */
   exposureTimesMinMaxRangeString()
   {
      let min = Math.min.apply( null, this.exposureTimes );
      let max = Math.max.apply( null, this.exposureTimes );
      if ( ( max - min ) < 1 )
         return format( "%.2fs", this.exposureTime );
      else
         return "[ " + this.exposureTimes.map( ( exposure ) => format( "%.2fs", exposure ) ).join( ', ' ) + " ]";
   }

   /**
    * Converts the color space to a string representation.
    *
    * This function returns a string representation of the color space for the group.
    * The color space can be RGB, Grayscale, or CFA (Color Filter Array).
    *
    * @returns {string} The color space as a string.
    */
   colorSpaceToString()
   {
      if ( this.isCFA )
      {
         if ( this.mode == BPP.GroupingMode.PRE )
            return "CFA";
         else
            return "RGB";
      }
      else return "mono";
   }

   /**
    * Logs the group context to the console.
    *
    * This function logs the group's properties (image type, size, binning,
    * filter, exposure time, keywords, mode, color space, and channel) to the console.
    */
   log()
   {
      // the number of frames is reported only if this is not an RGB combined image
      if ( this.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
         console.noteln( 'Group of ', this.fileItems.length, ' ', StackEngine.imageTypeToString( this.imageType ), ' frames (', this.activeFrames().length, ' active)' );
      console.noteln( 'SIZE  : ', this.sizeString() );
      console.noteln( 'BINNING  : ', this.binning );
      console.noteln( 'Filter   : ', this.filter.length > 0 ? this.filter : 'NoFilter' );
      console.noteln( 'Exposure : ', this.exposureTimesToString() );
      console.noteln( 'Keywords : [', this.keywordsToString(), ']' );
      console.noteln( 'Mode     : ', this.modeToString() );
      if ( this.imageType == ImageType.Flat || this.imageType == ImageType.Light )
         console.noteln( 'Color   : ', this.colorSpaceToString() );
      if ( this.associatedRGBchannel != null )
         console.noteln( 'Channel : ', this.associatedRGBchannel );
   }

   /**
    * Generates a log string header for the group.
    *
    * This function returns a string that can be used as a header in log messages.
    * The header includes the group ID, image type, filter, binning, exposure time, and size.
    *
    * @returns {string} The log string header for the group.
    */
   logStringHeader( title )
   {
      let activeCount = this.activeFrames().length;
      let header = '<b>********************</b> <i>' + title + '</i> <b>********************';
      this.footerLengthForCurrentHeader = header.length - '<b></b><i></i><b>'.length;
      let str = '<b>' + header + '\n';
      // the number of frames is reported only if this is not an RGB combined image
      if ( this.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
         str += 'Group of ' + this.fileItems.length + ' ' + StackEngine.imageTypeToString( this.imageType ) + ' frames (' + activeCount + ' active)\n';
      str += 'SIZE  : ' + this.sizeString();
      str += '\n' + 'BINNING  : ' + this.binning;
      if ( this.imageType != ImageType.Bias && this.imageType != ImageType.Dark )
         str += '\n' + 'Filter   : ' + ( this.filter.length > 0 ? this.filter : 'NoFilter' );
      if ( this.imageType != ImageType.Bias )
         str += '\n' + 'Exposure : ' + this.exposureTimesToString();
      str += '\n' + 'Keywords : [' + this.keywordsToString() + ']';
      str += '\n' + 'Mode     : ' + this.modeToString();
      if ( this.imageType == ImageType.Flat || this.imageType == ImageType.Light )
         str += '\n' + 'Color    : ' + this.colorSpaceToString();
      if ( this.associatedRGBchannel != null )
         str += '\n' + 'Channel  : ' + this.associatedRGBchannel;
      str += "</b>\n";
      return str;
   }

   /**
    * Generates a log string footer for the group.
    *
    * This function returns a string that can be used as a footer in log messages.
    * The footer includes the group ID and a summary of the group's properties, such as
    * the number of frames, total exposure time, and other relevant details.
    *
    * @returns {string} The log string footer for the group.
    */
   logStringFooter()
   {
      return '<b>' + '*'.repeat( this.footerLengthForCurrentHeader ) + '</b>\n';
   }

   /**
    * Converts the group to a string representation.
    *
    * This function returns a string representation of the group, including its
    * image type, filter, binning, exposure time, and size. This string can be used
    * for logging or debugging purposes to get a quick overview of the group's properties.
    *
    * @returns {string} The group as a string.
    */
   toString()
   {
      let a = [];
      a.push( "size = " + this.sizeString() );
      if ( !WBPPUtils.isEmptyString( this.filter ) )
         a.push( "filter = " + this.filter );
      else
         a.push( "filter = NoFilter" );
      a.push( "binning = " + this.binning.toString() );
      if ( this.exposureTimes.length == 1 )
         a.push( format( "exposure = %.2fs", this.exposureTime ) );
      else if ( this.exposureTimes.length > 1 )
         a.push( 'exposures = ', this.exposureTimesToString() );
      a.push( 'keywords = [' + this.keywordsToString() + "]" );
      a.push( 'mode = ' + this.modeToString() );
      if ( this.associatedRGBchannel != null )
         a.push( 'channel = ' + this.associatedRGBchannel );
      // the number of frames is reported only if this is not an RGB combined image
      if ( this.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
      {
         let activeCount = this.activeFrames().length;
         a.push( "frames = " + this.fileItems.length.toString() + " (" + activeCount + " active)" );
      }

      let s = StackEngine.imageTypeToString( this.imageType ) + " frames ";
      s += a[ 0 ];
      for ( let i = 1; i < a.length; ++i )
         s += ", " + a[ i ];
      return s;
   }

   /**
    * Converts the group to a short string representation.
    *
    * This function returns a concise string representation of the group, including its
    * image type, filter, binning, and exposure time. This string can be used for logging
    * or debugging purposes to get a quick overview of the group's key properties.
    *
    * @returns {string} The group as a short string.
    */
   toShortString( withActiveFrames, reportFileItems )
   {
      if ( withActiveFrames == undefined )
         withActiveFrames = true;
      if ( reportFileItems == undefined )
         reportFileItems = false;
      let a = [];
      a.push( this.sizeString() );
      if ( !WBPPUtils.isEmptyString( this.filter ) )
         a.push( this.filter );
      else
         a.push( "NoFilter" );
      a.push( this.colorSpaceToString() )
      a.push( this.binning.toString() + "x" + this.binning.toString() );
      if ( this.exposureTimes.length == 1 )
         a.push( format( "%.2fs", this.exposureTime ) );
      else if ( this.exposureTimes.length > 1 )
         a.push( this.exposureTimesToString() );
      let kw = this.keywordsToString();
      if ( kw.length > 0 )
         a.push( '[' + kw + "]" );
      if ( this.associatedRGBchannel != null )
         a.push( this.associatedRGBchannel );

      // the number of frames is reported only if this is not an RGB combined image
      let s = "";
      if ( withActiveFrames && this.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
      {
         let activeCount = this.activeFrames().length;
         a.push( "frames = " + this.fileItems.length.toString() + " (" + activeCount + " active)" );
      }
      if ( reportFileItems && this.associatedRGBchannel != BPP.AssociatedChannel.COMBINED_RGB )
         s = this.fileItems.length + " ";
      s += StackEngine.imageTypeToString( this.imageType ) + " frames, ";
      s += a[ 0 ];
      for ( let i = 1; i < a.length; ++i )
         s += ", " + a[ i ];
      if ( !s.endsWith( ")" ) )
         s += ")";
      return s;
   }

   /**
    * Converts the group to a short string representation for dropdown menus.
    *
    * This function returns a concise string representation of the group, including its
    * image type, filter, binning, and exposure time. This string is specifically formatted
    * for use in dropdown menus to provide a quick overview of the group's key properties.
    *
    * @returns {string} The group as a short string for dropdown menus.
    */
   dropdownShortString()
   {
      let retVal = "";
      switch ( this.imageType )
      {
         case ImageType.Bias:
            retVal = "BIN " + this.binning;
            break;
         case ImageType.Dark:
            retVal = "BIN " + this.binning + "   " + this.exposureToString();
            break;
         case ImageType.Flat:
         case ImageType.Light:
            retVal = this.filter + "  BIN " + this.binning + "  " + this.exposureToString();
            break;
      }
      return retVal;
   }

   /**
    * Converts the CFA pattern to a string representation.
    *
    * This function returns a string representation of the Color Filter Array (CFA) pattern
    * for the group. The CFA pattern is used in image processing to describe the arrangement
    * of color filters in a digital image sensor.
    *
    * @returns {string} The CFA pattern as a string.
    */
   CFAPatternString()
   {
      let patterns = [ "Auto", "RGGB", "BGGR", "GBRG", "GRBG", "GRGB", "GBGR", "RGBG", "BGRG" ];
      return patterns[ this.CFAPattern ];
   }

   /**
    * Converts the debayer method to a string representation.
    *
    * This function returns a string representation of the debayer method used for the group.
    * The debayer method is used in image processing to reconstruct a full-color image from
    * the raw data captured by a Color Filter Array (CFA) sensor.
    *
    * @returns {string} The debayer method as a string.
    */
   debayerMethodString()
   {
      let methods = [ "SuperPixel", "Bilinear", "VNG" ];
      return methods[ this.debayerMethod ];
   }

   /**
    * Returns a string listing all the group's keywords and values.
    * The list follows the global keywords definition order.
    *
    * @param {String} nameValueSeparator separator string between keyword name and value
    * @param {String} blockSeparator separator string between different key/values
    * @returns
    */
   keywordsToString( nameValueSeparator, blockSeparator )
   {
      let keywordsString = "";
      let separator = "";
      nameValueSeparator = nameValueSeparator || ": ";
      blockSeparator = blockSeparator || ", ";

      engine.keywords.names().forEach( name =>
      {
         if ( this.keywords[ name ] )
         {
            keywordsString += separator + name + nameValueSeparator + this.keywords[ name ];
            separator = blockSeparator;
         }
      } );
      return keywordsString;
   }

   /**
    * Generates a folder name for the group.
    *
    * This function returns a string that can be used as a folder name for the group.
    * The folder name is generated based on the group's properties, such as image type,
    * filter, binning, and exposure time. This ensures that the folder name is unique
    * and descriptive of the group's contents.
    *
    * @param {boolean} sanitized - If true, the folder name will be sanitized to remove any invalid characters.
    * @returns {string} The folder name for the group.
    */
   folderName( sanitized )
   {
      sanitized = sanitized != undefined ? sanitized : true;

      let imgType = StackEngine.imageTypeToString( this.imageType );
      let binning = "BIN-" + this.binning;
      let size = this.sizeString();
      let exposure = "EXPOSURE-" + format( "%.2f", this.exposureTime ) + "s";
      let filter = "FILTER-" + ( WBPPUtils.isEmptyString( this.filter ) ? "NoFilter" : WBPPUtils.cleanFilterName( this.filter ) );
      let colorSpace = this.colorSpaceToString();
      let keywordsPostFix = this.keywordsToString( "-" /* name/value separator */ , "_" /* block separator */ );

      let infos = [];
      switch ( this.imageType )
      {
         case ImageType.Bias:
            infos = [ imgType, binning, size ];
            break;
         case ImageType.Dark:
            infos = [ imgType, binning, size, exposure ];
            break;
         case ImageType.Flat:
            infos = [ imgType, binning, size, filter, colorSpace ];
            break;
         case ImageType.Light:
            if ( this.associatedRGBchannel )
            {
               infos = [ imgType, binning, size, exposure, filter, this.associatedRGBchannel ];
            }
            else
            {
               infos = [ imgType, binning, size, exposure, filter, colorSpace ];
            }
            break;
      }

      let fname = infos.join( "_" );
      if ( keywordsPostFix.length > 0 )
         fname = fname + "_" + keywordsPostFix;

      // sanitize the file name
      if ( sanitized )
      {
         let sanitizeRegExp = new RegExp( "[^" + BPP.Format.FOLDER_NAME_CHARSET + "]", "gi" );
         let sanitizedFName = fname.replace( sanitizeRegExp, '-' );
         console.writeln( "Sanitized group folder name: [", fname, "] -> [", sanitizedFName, "]" );
         return sanitizedFName;
      }
      else
      {
         return fname;
      }
   }

   /**
    * Converts the group mode to a string representation.
    *
    * This function returns a string representation of the mode for the group.
    * The mode can be one of several predefined modes, such as LIGHT, DARK, BIAS, or FLAT.
    * This string can be used for logging or debugging purposes to get a quick overview
    * of the group's mode.
    *
    * @returns {string} The group mode as a string.
    */
   modeToString()
   {
      switch ( this.mode )
      {
         case BPP.GroupingMode.PRE:
            return "calibration";
         case BPP.GroupingMode.POST:
            return "post-calibration";
      }
      return "-";
   }

   /**
    * Gets the size of the frames in the group.
    *
    * This function returns the size of the frames in the group as a number.
    * The size is calculated based on the width and height of the frames.
    *
    * @returns {number} The size of the frames in the group.
    */
   frameSize()
   {
      if ( this.mode == BPP.GroupingMode.PRE )
      {
         // in PRE all images are mono
         return this.size.width * this.size.height * 4;
      }
      else
      {
         // in POST images are mono if isCFA is false
         return this.size.width * this.size.height * 4 * ( this.isCFA ? 3 : 1 );
      }
   }

   /**
    * Gets the total memory size of the group in bytes.
    *
    * This function returns the total memory size of the group, computed as the
    * number of file items multiplied by the size of a single frame.
    *
    * @returns {number} The total memory size of the group in bytes.
    */
   groupSize()
   {
      return this.fileItems.length * this.frameSize();
   }

   /**
    * Gets the validation status of the group.
    *
    * This function checks calibration matching and configuration validity,
    * returning an object with diagnostic messages if issues are found.
    *
    * @returns {Object} Empty object if no issues, or an object with
    *    {errors: string} for critical problems or {warnings: string} for non-critical issues.
    */
   status()
   {
      if ( this.hasMaster && this.mode == BPP.GroupingMode.PRE )
      {
         return {};
      }

      let statusString = "";

      if ( this.mode == BPP.GroupingMode.PRE )
      {

         // CALIBRATION GROUP CHECKS

         // get the calibration groups
         let cg = engine.calibrationMatcher.getCalibrationGroupsFor( this );

         // ERROR CHECK: LIGHT
         if ( this.imageType == ImageType.Light )
         {
            // check if for any reason a master flat has different isCFA value than light group
            if ( cg.masterFlat && cg.masterFlat.isCFA != this.isCFA )
            {
               if ( this.isCFA )
                  statusString +=
                  "<p><b>Light frames are marked as CFA images but the Master Flat is not.</b><br>"
                  + "<i>Light frames mosaiced with a CFA pattern cannot be calibrated using a monochromatic Master Flat.</i></p>";
               else
                  statusString +=
                  "<p><b>Light frames are marked as monochromatic but the Master Flat is marked as a colorized CFA image.</b><br>"
                  + "<i>Monochromatic Light frames must be calibrated with a monochromatic Master Flat.</i></p>";
            }
         }

         // Returns errors immediately
         if ( statusString.length > 0 )
            return {
               errors: statusString
            };

         // CHECK: calibration files for FLAT
         if ( this.imageType == ImageType.Flat )
            if ( !cg.masterBias && !cg.masterDark )
               statusString +=
               "<p><b>Neither a Master Bias nor a Master Dark matches.</b><br>"
               + "<i>Flat frames will be integrated without being calibrated.</i></p>";

         // CHECK: calibration files for LIGHT
         if ( this.imageType == ImageType.Light )
         {
            if ( !cg.masterBias && !cg.masterDark )
            {
               if ( !cg.masterFlat )
                  statusString +=
                  "<p><b>No matching Master Bias, Master Dark and Master Flat found.</b><br>"
                  + "<i>Light frames will be integrated without being calibrated.</i></p>";
               else
                  statusString +=
                  "<p><b>Neither Bias nor Dark master file matches.</b><br>"
                  + "<i>Light frames will not be bias and/or dark subtracted before being calibrated by the Master Flat. This configuration may not completely calibrate Light frames.</i></p>";
            }

            // cosmetic correction

            if ( this.ccData.enabled )
            {
               if ( !cg.masterDark )
               {
                  statusString +=
                     "<p><b>Cosmetic correction enabled with a missing master dark.</b><br>"
                     + "<i>Cosmetic correction requires a master dark, with the current configuration it will not be applied to this group.</i></p>";
               }
               else
               {
                  let dT = Math.abs( cg.masterDark.exposureTime - this.exposureTime );
                  if ( dT > BPP.Defaults.ccMaxDarkExposureDiff )
                     statusString +=
                     "<p><b>Cosmetic correction enabled with a mismatching master dark.</b><br>"
                     + "<i>Cosmetic correction will use a master dark with a significant exposure time difference, this may lead to an inaccurate result.</i></p>";
               }
            }
            else
            { // CHECK: Cosmetic Correction icon name
               if ( this.ccData.CCTemplate && this.ccData.CCTemplate.length > 0 )
               {
                  if ( !WBPPUtils.validCCIconName( this.ccData.CCTemplate ) )
                     statusString +=
                     "<p><b>Reference to a non-existent Cosmetic Correction process icon name " + this.ccData.CCTemplate + ".</b><br>"
                     + "<i>Ensure that the specified Cosmetic Correction process icon exists otherwise Cosmetic Correction will not be performed. "
                     + "Alternatively, you may remove the reference.</i></p>";
               }
            }
         }

         // CHECK: current group is FLAT or LIGHT
         if ( this.imageType == ImageType.Flat || this.imageType == ImageType.Light )
         {
            // dark is optimized but bias is missing
            if ( !cg.masterBias && cg.masterDark && this.optimizeMasterDark )
               statusString +=
               "<p><b>Master Dark will be optimized but no Master Bias matches.</b><br>"
               + "<i>This configuration should be avoided since the optimization should be performed on a bias-subtracted Master Dark.</i></p>";

            // dark has different exposure time and it's not optimized
            if ( cg.masterDark )
            {
               let dT = Math.abs( cg.masterDark.exposureTime - this.exposureTime );
               if ( !this.optimizeMasterDark && dT > 5 )
               {
                  // main sentence
                  statusString +=
                     "<p><b>" + StackEngine.imageTypeToString( this.imageType ) + " frame's exposure differs from the Master Dark's exposure.</b><br>";
                  // suggestion:
                  if ( this.imageType == ImageType.Flat )
                  {
                     statusString += "<i>You can disable the use \"Dark\" checkbox and this will subtract the Master Bias only.</i></p>";
                  }
                  else if ( this.imageType == ImageType.Light )
                  {
                     if ( cg.masterBias )
                        statusString += "<i>You can optimize the Master Dark in order to achieve a better dark current estimation.</i></p>";
                     else
                        statusString += "<i>You can add a compatible Master Bias and optimize the Master Dark in order to achieve a better dark current estimation.</i></p>";
                  }
               }
            }
         }
      }
      else
      {
         // POST CALIBRATION GROUP CHECKS

         // check if group is drizzled but registration or image integration is not enabled
         if ( this.isDrizzleEnabled() && ( !engine.imageRegistration || !engine.integrate ) )
         {
            statusString += "<p>Drizzle Integration requires Image Registration and Image Integration to be enabled.</p>";
         }
      }

      return statusString.length > 0
         ?
         {
            warnings: statusString
         }
         :
         {};
   }

   // -------------------------------------------------------------------------
   // FRAME FILTER CONFIGURATION (for FrameSelection dialog)
   // -------------------------------------------------------------------------

   /**
    * Sets the frame filter configuration for this group.
    * Makes a deep copy to ensure each group has independent config.
    *
    * @param {Array} configs - Array of filter configurations, one per metric
    */
   setFrameFilterConfig( configs )
   {
      if ( !configs )
      {
         this.frameFilterConfig = null;
         return;
      }
      // Deep copy to ensure each group has its own independent config
      this.frameFilterConfig = [];
      for ( let i = 0; i < configs.length; i++ )
      {
         let src = configs[ i ];
         this.frameFilterConfig.push(
         {
            enabled: src.enabled,
            key: src.key,
            value: src.value,
            compareMode: src.compareMode,
            formula: src.formula,
            isCustomFormula: src.isCustomFormula
         } );
      }
   }

   /**
    * Gets the frame filter configuration for this group.
    * Returns a deep copy to prevent external modification of stored config.
    *
    * @returns {Array|null} Array of filter configurations or null if not set
    */
   getFrameFilterConfig()
   {
      if ( !this.frameFilterConfig )
         return null;
      // Return a deep copy to prevent external modification
      let copy = [];
      for ( let i = 0; i < this.frameFilterConfig.length; i++ )
      {
         let src = this.frameFilterConfig[ i ];
         copy.push(
         {
            enabled: src.enabled,
            key: src.key,
            value: src.value,
            compareMode: src.compareMode,
            formula: src.formula,
            isCustomFormula: src.isCustomFormula
         } );
      }
      return copy;
   }

   /**
    * Clears the frame filter configuration for this group.
    */
   clearFrameFilterConfig()
   {
      this.frameFilterConfig = null;
   }

   /**
    * Computes default filter configurations for this group based on its frame statistics.
    * All filters are disabled by default with threshold values set to accept all frames.
    * The threshold values are computed from the min/max of each metric in the group's activeFrames.
    *
    * @returns {Array} Array of default filter configurations
    */
   computeDefaultFilterConfigs()
   {
      let frames = this.activeFrames();
      let configs = [];

      for ( let i = 0; i < FrameFilterMetricDefinitions.length; i++ )
      {
         let metricDef = FrameFilterMetricDefinitions[ i ];

         // Custom formula filter - no computed value initially
         if ( metricDef.isCustomFormula )
         {
            configs.push(
            {
               enabled: false,
               key: metricDef.key,
               value: 0,
               compareMode: metricDef.defaultCompare,
               formula: "",
               isCustomFormula: true
            } );
            continue;
         }

         // Compute min/max for this metric from group's frames
         let minVal = Infinity,
            maxVal = -Infinity;
         for ( let j = 0; j < frames.length; j++ )
         {
            let descriptor = frames[ j ].descriptor
               ||
               {};
            // Use pre-computed normalized value for PSFSignalWeight
            let value;
            if ( metricDef.key === 'PSFSignalWeight' )
               value = descriptor.PSFSignalWeightNormalized;
            else
               value = descriptor.hasOwnProperty( metricDef.key ) ? descriptor[ metricDef.key ] : null;
            if ( value !== null && value !== undefined && !isNaN( value ) )
            {
               if ( value < minVal ) minVal = value;
               if ( value > maxVal ) maxVal = value;
            }
         }

         // Set default threshold based on compare mode (to accept all frames)
         let thresholdValue = 0;
         if ( isFinite( minVal ) && isFinite( maxVal ) )
         {
            if ( metricDef.defaultCompare === FrameFilterCompareMode.LESS_THAN )
               thresholdValue = maxVal; // Less than max accepts all
            else
               thresholdValue = minVal; // Greater than min accepts all
         }

         configs.push(
         {
            enabled: false,
            key: metricDef.key,
            value: thresholdValue,
            compareMode: metricDef.defaultCompare
         } );
      }

      return configs;
   }

   /**
    * Initializes this group with default filter configuration computed from its frame statistics.
    * Convenience method that computes defaults and saves them to the group.
    *
    * @returns {Array} The computed default filter configurations
    */
   initializeDefaultFilterConfig()
   {
      let configs = this.computeDefaultFilterConfigs();
      this.setFrameFilterConfig( configs );
      return configs;
   }

   /**
    * Clears/initializes the rejection state of all frames in this group.
    * Sets the 'rejected' property to false for all frame descriptors.
    * Note: Does NOT clear 'disabled' state - that is preserved across filter changes.
    */
   clearFrameRejectionState()
   {
      let frames = this.activeFrames();
      for ( let i = 0; i < frames.length; i++ )
      {
         let frame = frames[ i ];
         if ( frame.descriptor )
         {
            frame.descriptor.rejected = false;
            frame.setDescriptor( frame.descriptor );
         }
      }
   }

   /**
    * Clears both rejection and disabled state of all frames in this group.
    * Used when resetting the dialog to initial state.
    */
   clearAllFrameStates()
   {
      let frames = this.activeFrames();
      for ( let i = 0; i < frames.length; i++ )
      {
         let frame = frames[ i ];
         if ( frame.descriptor )
         {
            frame.descriptor.rejected = false;
            frame.descriptor.disabled = false;
            frame.setDescriptor( frame.descriptor );
         }
      }
   }

   /**
    * Gets the count of rejected frames in this group.
    *
    * @returns {number} Number of rejected frames
    */
   rejectedFrameCount()
   {
      let count = 0;
      let frames = this.activeFrames();
      for ( let i = 0; i < frames.length; i++ )
      {
         let descriptor = frames[ i ].descriptor
            ||
            {};
         if ( descriptor.rejected )
            count++;
      }
      return count;
   }

   /**
    * Gets the count of disabled frames in this group.
    * Disabled frames are manually excluded by the user and
    * are treated as rejected when the dialog is closed.
    *
    * @returns {number} Number of disabled frames
    */
   disabledFrameCount()
   {
      let count = 0;
      let frames = this.activeFrames();
      for ( let i = 0; i < frames.length; i++ )
      {
         let descriptor = frames[ i ].descriptor
            ||
            {};
         if ( descriptor.disabled )
            count++;
      }
      return count;
   }

   // -------------------------------------------------------------------------
   // CUSTOM FORMULA VALIDATION AND EVALUATION
   // -------------------------------------------------------------------------

   /**
    * Evaluates a custom formula for a single frame descriptor.
    * Formula is case-insensitive for variable names.
    * Uses Function constructor to avoid console warnings during evaluation.
    *
    * @param {string} formula - The formula expression
    * @param {Object} descriptor - Frame descriptor with metric values
    * @returns {number|null} Computed value or null if evaluation fails
    */
   evaluateCustomFormula( formula, descriptor )
   {
      if ( !formula || formula.trim().length === 0 || !descriptor )
         return null;

      // Normalize metric variable names
      let normalizedFormula = WBPPUtils.normalizeFormulaVariables( formula, CustomFormulaVariables );

      // Build variables object from descriptor
      let variables = {};
      for ( let i = 0; i < CustomFormulaVariables.length; i++ )
      {
         let variable = CustomFormulaVariables[ i ];
         let value = descriptor.hasOwnProperty( variable.key ) ? descriptor[ variable.key ] : 0;
         // Default to 0 for missing/invalid values
         if ( value === null || value === undefined || isNaN( value ) )
            value = 0;
         variables[ variable.name ] = value;
      }

      // Use the generic evaluator (uses Function constructor to avoid console warnings)
      let result = WBPPUtils.evaluateExpression( normalizedFormula, variables );

      // Validate the result
      if ( typeof result === "number" && !isNaN( result ) && isFinite( result ) )
         return result;

      return null;
   }

   /**
    * Applies a custom formula to all frames in this group.
    * Updates the 'custom' key in each frame's descriptor.
    *
    * @param {string} formula - The custom formula expression
    * @returns {boolean} True if formula was applied successfully
    */
   applyCustomFormula( formula )
   {
      let validation = WBPPUtils.validateExpression( formula, CustomFormulaVariables );
      if ( !validation.valid )
         return false;

      // Use activeFrames() to get properly constructed frames with correct descriptors
      let activeFrames = this.activeFrames();

      for ( let i = 0; i < activeFrames.length; i++ )
      {
         let frame = activeFrames[ i ];
         if ( !frame.descriptor )
            continue; // Skip frames without descriptors

         let value = this.evaluateCustomFormula( formula, frame.descriptor );
         frame.descriptor.custom = value;
         // Persist the descriptor changes
         frame.setDescriptor( frame.descriptor );
      }

      return true;
   }

   // -------------------------------------------------------------------------
   // FRAME FILTER APPLICATION
   // -------------------------------------------------------------------------

   /**
    * Tests a frame descriptor against the provided filter configurations.
    *
    * @param {Object} descriptor - Frame descriptor with metric values
    * @param {Array} filterConfigs - Array of filter configurations (optional, uses stored config if not provided)
    * @returns {boolean} True if frame passes all filters (not rejected)
    */
   testFrameAgainstFilters( descriptor, filterConfigs )
   {
      // Use stored config if not provided
      if ( !filterConfigs )
         filterConfigs = this.frameFilterConfig;

      if ( !filterConfigs || !descriptor )
         return true;

      for ( let i = 0; i < filterConfigs.length; i++ )
      {
         let config = filterConfigs[ i ];
         if ( !config.enabled )
            continue;

         let key = config.key;
         let value;

         // Use pre-computed normalized value for PSFSignalWeight
         if ( key === 'PSFSignalWeight' )
            value = descriptor.PSFSignalWeightNormalized;
         else
            value = descriptor.hasOwnProperty( key ) ? descriptor[ key ] : null;

         if ( value === null || value === undefined || isNaN( value ) )
            continue; // No value, don't reject

         let threshold = config.value;
         if ( isNaN( threshold ) )
            continue; // Invalid threshold, don't reject

         // Test against threshold
         let passes;
         if ( config.compareMode === FrameFilterCompareMode.LESS_THAN )
            passes = value < threshold;
         else
            passes = value > threshold;

         if ( !passes )
            return false;
      }
      return true;
   }

   /**
    * Applies the stored or provided filter configuration to all frames in this group.
    * Sets the 'rejected' property in each frame's descriptor based on filter results.
    * Optionally applies the custom formula before filtering if present in config.
    *
    * @param {Array} filterConfigs - Array of filter configurations (optional, uses stored config if not provided)
    * @returns {number} Number of rejected frames
    */
   applyFilters( filterConfigs )
   {
      // Use stored config if not provided
      if ( !filterConfigs )
         filterConfigs = this.frameFilterConfig;

      let rejectedCount = 0;

      // Clear rejection state before applying filters
      this.clearFrameRejectionState();

      // Apply custom formula if present and valid
      let customConfig = null;
      if ( filterConfigs )
      {
         for ( let i = 0; i < filterConfigs.length; i++ )
         {
            if ( filterConfigs[ i ].isCustomFormula && filterConfigs[ i ].enabled )
            {
               customConfig = filterConfigs[ i ];
               break;
            }
         }
      }
      if ( customConfig && customConfig.formula )
      {
         this.applyCustomFormula( customConfig.formula );
      }

      // Get active frames and apply filters
      let activeFrames = this.activeFrames();
      for ( let j = 0; j < activeFrames.length; j++ )
      {
         let frame = activeFrames[ j ];
         let descriptor = frame.descriptor;

         if ( !descriptor )
            continue;

         let passes = this.testFrameAgainstFilters( descriptor, filterConfigs );
         descriptor.rejected = !passes;
         frame.setDescriptor( descriptor );

         if ( !passes )
            rejectedCount++;
      }

      return rejectedCount;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-FrameGroup.js - Released 2026-05-10T11:05:00Z
