// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ExecutionCache.js - Released 2026-05-10T11:05:00Z
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

var EXECUTION_CACHE_CONSTANTS = {
   LMD_PREFIX: 'LMD_',
   HASH_CACHE_SIZE: 100 // Limit size of hash cache to prevent memory bloat
};

/**
 * This object is responsible for handling the WBPP execution cache.
 * The execution cache maintains a mapping of process configurations, input files,
 * and output files along with their last modified dates. This allows the system to
 * determine if a process needs to be re-executed or can be skipped because:
 * 1. The process configuration is unchanged
 * 2. Input files are unchanged (based on last modified dates)
 * 3. Output files already exist and are unchanged since last execution
 */
var ExecutionCache = class
{

   constructor()
   {
      this._hasher = new CryptographicHash( CryptographicHash.SHA1 );
      this._lmdPrefix = EXECUTION_CACHE_CONSTANTS.LMD_PREFIX;

      // Hash memoization cache
      this._hashCache = {
         keys: [],
         values:
         {},
         add: function( str, hash )
         {
            if ( this.keys.length >= EXECUTION_CACHE_CONSTANTS.HASH_CACHE_SIZE )
            {
               var oldestKey = this.keys.shift();
               delete this.values[ oldestKey ];
            }
            this.keys.push( str );
            this.values[ str ] = hash;
         }
      };

      this.reset();
   }

   /**
    * Generates a SHA1 hash-based cache key for the given string.
    * This is used to create unique identifiers for caching process configurations.
    * Implements memoization for frequently used strings.
    *
    * @param {String} string - The string to generate a cache key from
    * @return {String} The hexadecimal representation of the SHA1 hash
    */
   keyFor( string )
   {
      if ( this._hashCache.values[ string ] )
      {
         return this._hashCache.values[ string ];
      }
      var hash = this._hasher.hash( ByteArray.stringToUTF8( string ) ).toHex();
      this._hashCache.add( string, hash );
      return hash;
   }

   /**
    * Clears all cached data by resetting the internal cache object.
    */
   reset()
   {
      this.cache = {};
      this._hashCache.keys = [];
      this._hashCache.values = {};
   }

   // --- Internal fast-path methods (no validation, no logging) ---

   /** @private */
   _has( key )
   {
      return this.cache[ key ] !== undefined;
   }

   /** @private */
   _get( key )
   {
      return this.cache[ key ];
   }

   /** @private */
   _set( key, value )
   {
      this.cache[ key ] = value;
   }

   /** @private */
   _delete( key )
   {
      delete this.cache[ key ];
   }

   // --- Public API (validated, logged) ---

   /**
    * Checks if there is cached data associated with the given key.
    *
    * @param {String} key - The cache key to check
    * @return {Boolean} True if cache data exists for the key, false otherwise
    * @return Returns a safe default if key is invalid
    */
   hasCacheForKey( key )
   {
      if ( !key || typeof key !== 'string' )
         return false;
      return this.cache[ key ] !== undefined;
   }

   /**
    * Retrieves the cached data associated with the given key.
    *
    * @param {String} key - The cache key to retrieve data for
    * @return {*} The cached data if it exists, undefined otherwise
    * @return Returns a safe default if key is invalid
    */
   cacheForKey( key )
   {
      if ( !key || typeof key !== 'string' )
         return undefined;
      return this.cache[ key ];
   }

   /**
    * Sets the cache data for the given key.
    *
    * @param {String} key - The cache key to store data under
    * @param {*} value - The data to cache
    * @return Returns a safe default if key is invalid
    */
   setCache( key, value )
   {
      if ( !key || typeof key !== 'string' )
         return;
      this.cache[ key ] = value;
      console.writeln( "[cache] - Saved with key: ", key );
   }

   /**
    * Removes the cached data for the given key.
    *
    * @param {String} key - The cache key to remove
    * @return Returns a safe default if key is invalid
    */
   unsetCache( key )
   {
      if ( !key || typeof key !== 'string' )
         return;
      delete this.cache[ key ];
      console.writeln( "[cache] - Purged key: ", key );
   }

   /**
    * Checks if a file is unchanged since its last modified date was cached.
    * Compares the current last modified date with the cached one.
    *
    * @param {String} key - The cache key associated with the file
    * @param {String} filePath - The path to the file to check
    * @return {Boolean} True if the file is unchanged, false otherwise
    * @return Returns a safe default if parameters are invalid
    */
   isFileUnmodified( key, filePath )
   {
      if ( arguments.length !== 2 || !key || typeof key !== 'string' || !filePath || typeof filePath !== 'string' )
         return false;

      var LMD = this._get( this._lmdPrefix + key + filePath );
      if ( !LMD )
      {
         console.writeln( "[cache] - File has changed <raw>"
            + File.extractNameAndExtension( filePath ) + "</raw>"
            + " [ ", key, " ] - cached [", LMD, "]" );
         return false;
      }
      var currentLMD = WBPPUtils.getLastModifiedDate( filePath );
      var result = currentLMD !== undefined && currentLMD === LMD;

      console.writeln( "[cache] - File ",
         ( result ? "is unmodified" : "has changed" ),
         " <raw>" + File.extractNameAndExtension( filePath ) + "</raw>",
         " [ ", key, " ] - cached [", LMD, "] - current [", currentLMD, "]"
      );

      return result;
   }

   /**
    * Stores the last modified date of a file in the cache.
    * Only caches the date if the file exists.
    *
    * @param {String} key - The cache key to associate with the file
    * @param {String} filePath - The path to the file to cache
    * @return Returns a safe default if parameters are invalid
    */
   cacheFileLMD( key, filePath )
   {
      if ( arguments.length !== 2 || !key || typeof key !== 'string' || !filePath || typeof filePath !== 'string' )
         return;

      var LMD = WBPPUtils.getLastModifiedDate( filePath );
      if ( LMD )
      {
         var cacheKey = this._lmdPrefix + key + filePath;
         console.writeln( "[cache] - Set LMD [", key, "] <raw>"
            + File.extractNameAndExtension( filePath ) + "</raw>: ", LMD );
         this._set( cacheKey, LMD );
         this.__trackLMDKeys( filePath, cacheKey, LMD );
      }
   }

   /**
    * Invalidates the cached last modified date for the given file and key combination.
    * This removes the cached LMD entry and updates the file history tracking.
    *
    * @param {String} key - The cache key associated with the file
    * @param {String} filePath - The path to the file to invalidate
    */
   invalidateFileLMD( key, filePath )
   {
      if ( arguments.length !== 2 || !key || typeof key !== 'string' || !filePath || typeof filePath !== 'string' )
         return;
      console.writeln( "[cache] - invalidate LMD [", key, "] <raw>" + File.extractNameAndExtension( filePath ) + "</raw>" );
      let cacheKey = this._lmdPrefix + key + filePath;
      this._delete( cacheKey );
      this.__trackLMDKeys( filePath, cacheKey, undefined );
   }

   /**
    * Exports the entire cache to a JSON string representation.
    *
    * @return {String} JSON string representation of the cache
    */
   toString()
   {
      let seen = new Set();
      return JSON.stringify( this.cache, function( key, value )
      {
         if ( key === "keySet" )
            return undefined;
         if ( typeof value === "object" && value !== null )
         {
            if ( seen.has( value ) )
               return undefined;
            seen.add( value );
         }
         return value;
      }, 2 );
   }

   /**
    * Reconstructs the cache from a JSON string representation.
    * If parsing fails, the cache will be reset and a warning logged.
    *
    * @param {String} string - JSON string representation of the cache
    */
   fromString( string )
   {
      try
      {
         this.cache = JSON.parse( string );
      }
      catch ( e )
      {
         this.reset();
         console.warningln( "** Warning: Execution cache parsing failed." )
      }
   }

   /**
    * Returns the approximate size of the cache in bytes.
    * Computed by serializing the cache to JSON. Falls back to an estimate
    * based on key count if serialization fails.
    *
    * @return {Number} Approximate size of the cache in bytes
    */
   size()
   {
      try
      {
         return this.toString().length;
      }
      catch ( e )
      {
         return Object.keys( this.cache ).length * 100;
      }
   }

   /**
    * Internal function that maintains a history of file modifications and their associated cache keys.
    * This tracking enables updating cached LMDs when a file changes in ways that shouldn't invalidate the cache.
    *
    * @param {String} filePath - The path to the file being tracked
    * @param {String} key - The cache key associated with this LMD
    * @param {String} LMD - The last modified date to track
    * @private
    */
   __trackLMDKeys( filePath, key, LMD )
   {
      var fileHistory = this._get( filePath );

      if ( !fileHistory || !fileHistory.length )
      {
         this._set( filePath, [
         {
            lmd: LMD,
            keys: [ key ],
            keySet: { [key]: true }
         } ] );
         return;
      }

      var lastEntry = fileHistory[ fileHistory.length - 1 ];
      if ( lastEntry.lmd === LMD )
      {
         // Lazy-init keySet for entries loaded from serialized cache
         if ( !lastEntry.keySet )
         {
            lastEntry.keySet = {};
            for ( let i = 0; i < lastEntry.keys.length; ++i )
               lastEntry.keySet[ lastEntry.keys[ i ] ] = true;
         }
         if ( !lastEntry.keySet[ key ] )
         {
            lastEntry.keys.push( key );
            lastEntry.keySet[ key ] = true;
         }
      }
      else
      {
         fileHistory.push(
         {
            lmd: LMD,
            keys: [ key ],
            keySet: { [key]: true }
         } );
      }

      this._set( filePath, fileHistory );
   }

   /**
    * Updates all cached LMD entries for a file from a previous value to a new value.
    * This is particularly useful when file modifications (like astrometric solution updates)
    * shouldn't invalidate the cache.
    *
    * @param {String} filePath - The path to the file being updated
    * @param {String} previousLMD - The previous last modified date to match
    * @param {String} newLMD - The new last modified date to set
    */
   updateLMD( filePath, previousLMD, newLMD )
   {
      let fileHistory = this._get( filePath );
      if ( fileHistory === undefined || fileHistory.length === 0 )
         return;
      for ( let i = 0; i < fileHistory.length; ++i )
      {
         if ( fileHistory[ i ].lmd === previousLMD )
         {
            let keys = fileHistory[ i ].keys;
            for ( let j = 0; j < keys.length; ++j )
               this._set( keys[ j ], newLMD );
            fileHistory[ i ].lmd = newLMD;
            this._set( filePath, fileHistory );
            return;
         }
      }
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-ExecutionCache.js - Released 2026-05-10T11:05:00Z
