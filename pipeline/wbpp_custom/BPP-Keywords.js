// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Keywords.js - Released 2026-05-10T11:05:00Z
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
 * Keyword constructor: defines a keyword by name and mode mask.
 *
 * @param {String} name
 * @param {WBPPKeywordMode} mode
 */
var Keyword = class
{
   constructor( name, mode )
   {
      this.name = name;
      this.mode = mode;
   }
}

// ----------------------------------------------------------------------------

/**
 * Manages the list of keywords and provides helpers for
 * adding/replacing/removing/sorting and searching keywords.
 * Duplicates and empty keywords are not allowed.
 */
var Keywords = class
{

   constructor()
   {
      this.list = [];
   }

   /**
    * Safely add a new keyword and checks for duplicates and empty keyword.
    *
    * @param {String} name
    * @param {String?} mode keyword mode, pre-processing only as default
    * @returns undefined on success, error message in case of error
    */
   add( name, mode )
   {
      // default mode is pre-processing only
      mode = ( mode !== undefined && mode !== null ) ? mode : BPP.KeywordMode.PRE;
      if ( name.length == 0 )
         return "Unable to add an empty keyword.";
      if ( this.contains( name ) )
         return "Keyword \"" + name + "\" is already in the list.";
      this.list.push( new Keyword( name, mode ) );
      return undefined;
   }

   /**
    * Replace an existing keyword name.
    * If the new name to be assigned collides with an existing keywords then
    * the replacement does not occur and the function silently returns.
    *
    * @param {String} oldName
    * @param {String} newName
    */
   replace( oldName, newName )
   {
      if ( this.contains( newName ) )
         return;
      this.list.forEach( kw =>
      {
         if ( kw.name == oldName )
            kw.name = newName
      } );
   }

   /**
    * Removes a keyword with the given name.
    *
    * @param {String} name
    */
   remove( name )
   {
      this.list = this.list.filter( k => k.name != name );
   }

   /**
    * Moves a keyword up or down in the list.
    *
    * @param {*} name
    * @param {*} up true to move keyword in the previous position, false to move it in the next
    * @return the new index of the keyword
    */
   move( name, up )
   {
      let indx = this.list.reduce( ( obj, keyword, index ) =>
      {
         return keyword.name == name ? index : obj;
      }, -1 );
      if ( indx == -1 )
         return undefined;

      // do nothing if the keyword would move out of bounds
      if ( ( indx == 0 && up ) || ( indx == this.list.length - 1 && !up ) )
         return undefined;
      let dstIndx = indx + ( up ? -1 : 1 );
      let tmp = this.list[ dstIndx ];
      this.list[ dstIndx ] = this.list[ indx ];
      this.list[ indx ] = tmp;
      return dstIndx;
   }

   /**
    * Checks if a keyword with the given name exists.
    *
    * @param {string} name
    * @returns Boolean
    */
   contains( name )
   {
      return this.list.map( k => k.name ).indexOf( name ) > -1;
   }

   /**
    * Filters the given keywords object accordingly to the current keywords configuration.
    * Always returns an empty object if keywords are globally disabled.
    *
    * @param {{String:String}} keywords keywords to be filtered
    * @param {WBPPKeywordMode} mode filtering mode
    * @returns {String:Setting} filtered keywords
    */
   filterKeywordsForMode( keywords, mode )
   {
      if ( !engine.groupingKeywordsEnabled || !keywords )
      {
         return {};
      }
      let namesForMode = this.list.reduce( ( obj, keyword ) =>
      {
         if ( keyword.mode & mode )
            obj.push( keyword.name );
         return obj;
      }, [] );

      // return the keywords enabled for the given mode
      return Object
         .keys( keywords )
         .filter( name => ( namesForMode.indexOf( name ) != -1 ) )
         .reduce( ( obj, name ) =>
         {
            obj[ name ] = keywords[ name ];
            return obj;
         },
         {} );
   }

   /**
    * Returns the keywords object containing only the keywords enabled for the given mode.
    *
    * @param {number} mode a BPP.GroupingMode bitmask
    */
   keywordsForMode( mode )
   {
      return this.list.filter( kw => kw.mode & mode );
   }

   /**
    * Switches the mode of the given keyword.
    *
    * @param {String} name
    */
   switchMode( name )
   {
      let keyword = this.list.filter( kw => kw.name == name );
      if ( keyword.length == 0 )
         return;
      // manually control the loop cycle
      switch ( keyword[ 0 ].mode )
      {
         case BPP.KeywordMode.NONE:
            keyword[ 0 ].mode = BPP.KeywordMode.PRE;
            break;
         case BPP.KeywordMode.PRE:
            keyword[ 0 ].mode = BPP.KeywordMode.PREPOST;
            break;
         case BPP.KeywordMode.PREPOST:
            keyword[ 0 ].mode = BPP.KeywordMode.POST;
            break;
         case BPP.KeywordMode.POST:
            keyword[ 0 ].mode = BPP.KeywordMode.NONE;
            break;
      }
   }

   /**
    * Returns a flat list of all keyword names
    */
   names()
   {
      return this.list.map( k => k.name );
   }

   /**
    * Returns the alphabetically sorted list of keyword names whose mode
    * includes the given grouping mode. Uses a bitmask match so that keywords
    * with mode PREPOST are included when querying for either PRE or POST.
    *
    * @param {number} mode a BPP.GroupingMode value (PRE or POST)
    * @return {String[]} sorted keyword names matching the given mode
    */
   sortedNames( mode )
   {
      let keywords = this.list.filter( k => k.mode & mode ).map( k => k.name );
      keywords.sort();
      return keywords;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-Keywords.js - Released 2026-05-10T11:05:00Z
