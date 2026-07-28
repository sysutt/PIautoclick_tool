// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-FrameGroupsManager.js - Released 2026-05-10T11:05:00Z
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
 * This object is responsible of managing multiple grouping strategies. In the current implementation only two
 * kind of grouping are implemented: pre-processing and post-processing grouping.
 * Any file should be added using this manager, in such way the file is added to all managed groupings in order
 * to quickly switch between the two later.
 * Any time the list of groups for a grouping strategy is needed you just need to use the groupsForMode function
 * providing the grouping mode and it will return the corresponding list of groups.
 */
var FrameGroupsManager = class
{

   constructor()
   {
      // groups
      this.groups = [];
      this.cache = {};
   }

   /**
    * Initialize all data for processing
    *
    */
   initializeProcessing()
   {
      this.groups.forEach( group =>
      {
         group.initForProcessing();
         // Clear frame rejection state from previous runs
         group.clearFrameRejectionState();
         group.fileItems.forEach( item => item.initForProcessing() );
      } );
   }

   /**
    * Adds a new group with the given properties.
    *
    * @param {ImageType} imageType
    * @param {String} filter
    * @param {Number} binning
    * @param {Number} exposureTime
    * @param {Object} size {width:Numeric, height:Numeric}
    * @param {Boolean} isCFA
    * @param {String} fileItem
    * @param {Boolean} isMaster
    * @param {{String:String}?} keywords
    * @param {WBPPGroupingMode} mode
    */
   addGroup( imageType, filter, binning, exposureTime, size, isCFA, fileItem, isMaster, keywords, mode )
   {
      // append the new group
      this.groups.push( new FrameGroup(
         imageType,
         filter,
         binning,
         exposureTime,
         size,
         isCFA,
         fileItem,
         isMaster,
         keywords,
         mode ) );
   }

   /**
    * Adds a new file item. customKeywords and customModes are used by Linear
    * Pattern Subtraction in order to regroup frames by binning, exposure and filter name
    * ignoring the keywords and keep the new generated groups separated form the pre and post
    * groups.
    *
    * @param {FileItem} fileItem
    * @param {*} customKeywords
    * @param {*} customModes
    * @param {*} customCFA
    * @returns
    */
   addFileItem( fileItem, customKeywords, customModes, customCFA )
   {
      // only light frames are added to both pre and post process modes. Bias, Dark and Flat are added only to pre-process mode.
      let modes = customModes || ( fileItem.imageType == ImageType.Light ? [ BPP.GroupingMode.PRE, BPP.GroupingMode.POST ] : [ BPP.GroupingMode.PRE ] );
      let isCFA = customCFA == undefined ? fileItem.isCFA : customCFA;

      // for all modes iterate and add the file
      modes.forEach( mode =>
      {
         let size = fileItem.matchingSizes[ mode ];

         let group = engine.findGroup(
            fileItem.imageType,
            fileItem.filter,
            fileItem.binning,
            fileItem.exposureTime,
            size,
            fileItem.isMaster,
            isCFA,
            engine.darkExposureTolerance,
            mode == BPP.GroupingMode.PRE ? engine.lightExposureTolerance : engine.lightExposureTolerancePost,
            customKeywords || fileItem.keywords,
            true, /* strictKeywordsMatching */
            mode
         );

         // add the item if a group has been found, create a new group otherwise
         if ( group )
         {
            group.appendFileItem( fileItem, true /* ignoreCFAMatching */ );
         }
         else
            this.addGroup(
               fileItem.imageType,
               fileItem.filter,
               fileItem.binning,
               fileItem.exposureTime,
               size,
               isCFA,
               fileItem,
               fileItem.isMaster,
               customKeywords || fileItem.keywords,
               mode );
      } );

      return {
         success: true
      };
   }

   /**
    * Returns the group with the provided id.
    *
    * @param {String} id the id that the returned group has
    * @returns the group with the provided id
    */
   getGroupByID( id )
   {
      let matching = this.groups.filter( g => g.id == id );
      return matching.length == 1 ? matching[ 0 ] : undefined;
   }

   /**
    * Returns the list of group matching the given mode
    *
    * @param {WBPPGroupingMode} mode
    * @returns
    */
   groupsForMode( mode )
   {
      return this.groups.filter( group =>
      {
         return group && group.mode == mode
      } )
   }

   /**
    * Returns the list of different binnings of the calibration groups.
    *
    * @returns an array of integers representing the different binnings of the calibration groups
    */
   binningsOfCalibrationGroups()
   {
      let groups = this.groupsForMode( BPP.GroupingMode.PRE );
      return groups.reduce( ( acc, group ) =>
      {
         if ( group.imageType == ImageType.Light && acc.indexOf( group.binning ) == -1 )
         {
            acc.push( group.binning );
         }
         return acc;
      }, [] );
   }

   /**
    * Removes a group given its index and mode.
    *
    * @param {Numeric} i group index
    */
   removeGroupAtIndex( i )
   {

      // sanitize overrides i.e. clear any override that references the group
      if ( this.groups[ i ] && this.groups[ i ].mode == BPP.GroupingMode.PRE )
      {
         let id = this.groups[ i ].id;
         delete this.cache[ id ];
         this.groups.forEach( group =>
         {
            if ( !group.overrideDark || group.overrideDark.id == id )
            {
               group.overrideDark = undefined;
            }
            if ( !group.overrideFlat || group.overrideFlat.id == id )
            {
               group.overrideFlat = undefined;
            }
         } );
      }

      // remove the group from the list
      this.groups.splice( i, 1 );
   }

   /**
    * Delete all groups of the given type and mode.
    *
    * @param {ImageType} imageType
    * @param {WBPPGroupingMode?} mode optional, if undefined all modes are matched
    */
   deleteFrameSet( imageType, mode )
   {
      for ( let i = 0; i < this.groups.length; ++i )
         // use mode only if defined
         if ( this.groups[ i ].imageType == imageType && this.groups[ i ].mode == ( mode || this.groups[ i ].mode ) )
            this.removeGroupAtIndex( i-- );
   }

   /**
    * Removes all groups.
    *
    */
   clear()
   {
      this.groups = [];
   }

   /**
    * Convenience checked for empty groups
    */
   isEmpty()
   {
      return this.groups.length == 0;
   }

   /**
    * Clears the groups properties cache.
    *
    */
   clearCache()
   {
      this.cache = {}
   }

   /**
    * Returns customizable options for all groups. The object returned has the group id
    * as value and an object containing the properties as value.
    *
    * @returns
    */
   cacheGroupsProperties()
   {
      // store all cachable properties for each group by ID
      this.groups.forEach( group =>
      {
         if ( group && group.id ) // for compatibility with WBPP 1.x
         {
            this.cache[ group.id ] = {
               optimizeMasterDark: group.optimizeMasterDark,
               isCFA: group.isCFA,
               CFAPattern: group.CFAPattern,
               debayerMethod: group.debayerMethod,
               lightOutputPedestalMode: group.lightOutputPedestalMode,
               lightOutputPedestal: group.lightOutputPedestal,
               drizzleData: group.drizzleData,
               fastIntegrationData: group.fastIntegrationData,
               ccData: group.ccData,

               forceNoDark: group.forceNoDark,
               forceNoFlat: group.forceNoFlat,
               overrideDarkID: group.overrideDark && group.overrideDark.id,
               overrideFlatID: group.overrideFlat && group.overrideFlat.id,

               __reference_frame__: group.__reference_frame__,
               __ln_reference_frame__: group.__ln_reference_frame__,

               // Frame selection filter configuration
               frameFilterConfig: group.frameFilterConfig,
            };
         }
      } );
   }

   /**
    * Restores customizable groups options from an object. The object should be
    * generated by the getGroupsProperties function.
    *
    * @param {*} mode optional, the group mode to be restored
    */
   restoreGroupsPropertiesFromCache( mode )
   {
      let groups = mode != undefined ? this.groupsForMode( mode ) : this.groups;
      groups.forEach( group =>
      {
         let properties = this.cache[ group.id ];
         if ( properties )
         {
            group.optimizeMasterDark = properties.optimizeMasterDark;
            group.isCFA = properties.isCFA;
            group.CFAPattern = properties.CFAPattern;
            group.debayerMethod = properties.debayerMethod;
            group.lightOutputPedestalMode = properties.lightOutputPedestalMode;
            group.lightOutputPedestal = properties.lightOutputPedestal;
            group.setDrizzleData( properties.drizzleData );
            group.setFastIntegrationData( properties.fastIntegrationData );
            group.setCcData( properties.ccData );

            group.forceNoDark = properties.forceNoDark;
            group.forceNoFlat = properties.forceNoFlat;
            group.overrideDark = this.getGroupByID( properties.overrideDarkID );
            group.overrideFlat = this.getGroupByID( properties.overrideFlatID );

            group.__reference_frame__ = properties.__reference_frame__;
            group.__ln_reference_frame__ = properties.__ln_reference_frame__;

            // Restore frame selection filter configuration (use setter for deep copy)
            if ( properties.frameFilterConfig !== undefined )
               group.setFrameFilterConfig( properties.frameFilterConfig );
         }
      } );
   }

   /**
    * Returns the total light frames integration time.
    *
    * @returns
    */
   totalIntegrationTime()
   {
      return this.groupsForMode( BPP.GroupingMode.POST ).reduce( ( acc, group ) =>
      {
         // monochromatic groups always add
         if ( !group.isCFA && group.associatedRGBchannel == null )
         {
            return acc + group.totalExposureTime();
         }

         // if separate RGB channels only is active then we count only the _R channel
         if ( engine.debayerOutputMethod == BPP.DebayerOutputMode.SEPARATED && group.associatedRGBchannel == BPP.AssociatedChannel.R )
         {
            return acc + group.totalExposureTime();
         }

         // if combined RGB channels is active then we count only the RGB channel
         if ( engine.debayerOutputMethod != BPP.DebayerOutputMode.SEPARATED && group.associatedRGBchannel == null )
         {
            return acc + group.totalExposureTime();
         }

         // left the count unchanged
         return acc;

      }, 0 );
   }

   /**
    * Returns the whole list of file items in the session.
    *
    * @returns
    */
   allFileItems()
   {
      return this.groupsForMode( BPP.GroupingMode.PRE ).reduce( ( acc, g ) =>
      {
         return acc.concat( g.fileItems );
      }, [] );
   }

   /**
    * Returns the fileItem in the session that matches the provided filePath.
    * If none or more than one item are found then returns undefined.
    *
    * @param {*} filePath
    */
   getReferenceFrameFileItem( filePath )
   {
      let items = this.allFileItems();
      for ( let i = 0; i < items.length; ++i )
         if ( items[ i ].filePath == filePath )
            return items[ i ];
      return undefined;
   }

   /**
    * Returns true if at least one post-process group configured with a regular integration
    * exists (i.e. Fast Integration is disabled).
    */
   regularIntegrationGroupExists()
   {
      let postGroups = this.groupsForMode( BPP.GroupingMode.POST );
      for ( let i = 0; i < postGroups.length; ++i )
         if ( !postGroups[ i ].fastIntegrationData.enabled )
            return true;
      return false;
   }

   /**
    * Returns true if at least one post-process group configured with fast integration
    * exists.
    */
   fastIntegrationGroupExists()
   {
      let postGroups = this.groupsForMode( BPP.GroupingMode.POST );
      for ( let i = 0; i < postGroups.length; ++i )
         if ( postGroups[ i ].fastIntegrationData.enabled )
            return true;
      return false;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-FrameGroupsManager.js - Released 2026-05-10T11:05:00Z
