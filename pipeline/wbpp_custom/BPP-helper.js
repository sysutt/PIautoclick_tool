// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Helper.js - Released 2026-05-10T11:05:00Z
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

/*
 * DMSangle: Helper class for angles in degrees/minutes/seconds format.
 * Fallback definition used before pjsr/astrometry/DMath.js is loaded
 * (BPP-Helper.js is included before BPP-Solver.js in the include chain).
 * Overridden by the V8 class version from DMath.js when AstrometricMetadata
 * is included via BPP-Solver.js.
 */
if ( typeof DMSangle === 'undefined' )
{
   var DMSangle = function()
   {
      this.deg = 0;
      this.min = 0;
      this.sec = 0;
      this.sign = 1;

      this.GetValue = function()
      {
         return this.sign * ( this.deg + ( this.min + this.sec / 60 ) / 60 );
      };

      this.ToString = function( hours, precision )
      {
         if ( precision === undefined )
            precision = 2;
         if ( hours )
            ++precision;
         let secWidth = 2;
         if ( precision > 0 )
            secWidth += 1 + precision;
         let plus = hours ? "" : "+";
         if ( this.deg != null && this.min != null && this.sec != null && this.sign != null )
            return ( ( this.sign < 0 ) ? "-" : plus ) +
                   format( "%02d %02d %0*.*f", this.deg, this.min, secWidth, precision, this.sec );
         return "<* invalid *>";
      };
   };

   DMSangle.FromString = function( coordStr, mindeg, maxdeg, noSecs )
   {
      let match = coordStr.match( noSecs ? "'?([+-]?)([0-9]*)[ :]([0-9]*(\\.?[0-9]*)?)'?" :
                                            "'?([+-]?)([0-9]*)[ :]([0-9]*)[ :]([0-9]*(\\.?[0-9]*)?)'?" );
      if ( match == null )
         return null;
      let coord = new DMSangle();
      if ( match.length < ( noSecs ? 3 : 4 ) )
         throw new Error( "Invalid coordinates" );
      coord.deg = parseInt( match[2], 10 );
      if ( coord.deg < mindeg || coord.deg > maxdeg )
         throw new Error( "Invalid coordinates" );
      coord.min = parseInt( match[3], 10 );
      if ( coord.min < 0 || coord.min >= 60 )
         throw new Error( "Invalid coordinates (minutes)" );
      if ( noSecs )
         coord.sec = 0;
      else
      {
         coord.sec = parseFloat( match[4] );
         if ( coord.sec < 0 || coord.sec >= 60 )
            throw new Error( "Invalid coordinates (seconds)" );
      }
      coord.sign = ( match[1] == '-' ) ? -1 : 1;
      return coord;
   };

   DMSangle.FromAngle = function( angle )
   {
      let coord = new DMSangle();
      if ( angle < 0 )
      {
         coord.sign = -1;
         angle = -angle;
      }
      coord.deg = Math.trunc( angle );
      coord.min = Math.trunc( ( angle - coord.deg ) * 60 );
      coord.sec = ( angle - coord.deg - coord.min / 60 ) * 3600;
      if ( coord.sec > 59.999 )
      {
         coord.sec = 0;
         coord.min++;
         if ( coord.min == 60 )
         {
            coord.min = 0;
            coord.deg++;
         }
      }
      return coord;
   };
}

/*
 * Helper routines
 */

var helperFunctions = () => (
{
   /**
    * Returns true if the version string a is lower than b.
    *
    * @param {*} a
    * @param {*} b
    * @return {*}
    */
   versionLT: ( a, b ) =>
   {
      let at = a.split( "." ).map( i => parseInt( i ) );
      let bt = b.split( "." ).map( i => parseInt( i ) );
      for ( let i = 0; i < Math.max( at.length, bt.length ); i++ )
      {
         let ai = ( at[ i ] || 0 );
         let bi = ( bt[ i ] || 0 );
         if ( bi > ai )
            return true;
         if ( bi < ai )
            return false;
      }
      return false;
   },

   /**
    *
    * @returns The path to the file containing the persisted cache
    */
   cacheFName: () =>
   {
      return CoreApplication.configDirPath + "/WeightedBatchPreprocessing-" + format( "%03i", CoreApplication.instance ) + "-pxi.cache";
   },

   /**
    * Returns an array of enabled target frames.
    * Used to build the input for ImageCalibration/ImageIntegration/StarAlignment
    */
   enableTargetFrames: function( array, nColumns, enableDrizzle, enableLN )
   {
      // V8/PI >=1.9.x: ImageIntegration.images requires 4 columns per row:
      // [enabled, filePath, drizzlePath, localNormalizationPath]
      // Ensure we always produce at least 4 columns when nColumns == 2 (II format).
      let actualColumns = Math.max( nColumns, 4 );
      let target = new Array;
      for ( let i = 0; i < array.length; ++i )
      {
         target[ i ] = new Array( actualColumns );
         for ( let j = 0; j < nColumns - 1; ++j )
            target[ i ][ j ] = true;

         let filePath;
         if ( typeof array[ i ] == 'string' )
            filePath = array[ i ];
         else
            filePath = array[ i ].current;

         target[ i ][ nColumns - 1 ] = filePath;

         // drizzle path
         if ( enableDrizzle )
            target[ i ][ nColumns ] = File.changeExtension( filePath, '.xdrz' );
         else if ( actualColumns > nColumns )
            target[ i ][ nColumns ] = "";

         // local normalization path
         if ( enableLN )
         {
            if ( typeof array[ i ] != 'string' && array[ i ].localNormalizationFile != undefined )
               target[ i ][ nColumns + 1 ] = array[ i ].localNormalizationFile;
            else
               target[ i ][ nColumns + 1 ] = File.changeExtension( filePath, '.xnml' );
         }
         else if ( actualColumns > nColumns + 1 )
            target[ i ][ nColumns + 1 ] = "";

         // fill any remaining columns with empty strings
         for ( let j = nColumns + 2; j < actualColumns; ++j )
            target[ i ][ j ] = "";
      }
      return target;
   },

   /**
    * Checks if a valid Cosmetic Correction icon name is provided by checking the
    * existence of a correspondent valid icon on the workspace.
    *
    * @param {*} name the Cosmetic Correction icon name to be checked
    * @return {*} true if a valid Cosmetic Correction icon exists, false otherwise
    */
   validCCIconName: function( name )
   {
      let icons = ProcessInstance.iconsByProcessId( "CosmeticCorrection" );
      for ( let i = 0; i < icons.length; ++i )
         if ( name == icons[ i ] )
            return true;
      return false;
   },

   // ----------------------------------------------------------------------------
   // String Utils
   // ----------------------------------------------------------------------------

   /**
    * Returns a string describing the count of resulted files.
    *
    * @param {Number} nCached the number of cached files
    * @param {Number} nCreated the number of created files
    * @param {Number} nFailed the number of failed files
    * @param {String} generatedLabel the optional label to be used for generated files
    * @return {String} the readable string
    */
   resultCountToString: function( nCached, nCreated, nFailed, generatedLabel )
   {
      if ( nCached == 0 && nFailed == 0 && generatedLabel == undefined )
         return "";

      let result = "";
      let separator = "";

      if ( nCreated > 0 )
      {
         result += nCreated + " " + ( generatedLabel || "created" );
         separator = ", ";
      }
      if ( nCached > 0 )
      {
         result += separator + nCached + " cached";
         separator = ", ";
      }
      if ( nFailed > 0 )
         result += separator + nFailed + " failed";

      return result;
   },
   /**
    * Returns a string representing the current time stamp.
    *
    */
   timestampString: function()
   {
      let logDate = new Date;
      return format( "%04d%02d%02d%02d%02d%02d",
         logDate.getUTCFullYear(), logDate.getUTCMonth() + 1, logDate.getUTCDate(),
         logDate.getUTCHours(), logDate.getUTCMinutes(), logDate.getUTCSeconds() );
   },
   /**
    * Returns a h:mm:s formatted string representing the value as a duration
    *
    * @param {*} value
    */
   formatTimeDuration: function( duration )
   {
      let hours = Math.floor( duration / 3600 );
      let min = Math.floor( ( duration - hours * 3600 ) / 60 );
      let sec = duration % 60;
      return format( "%4dh %2dm %2.0fs", hours, min, sec );
   },

   /**
    * Returns a string representing a human-readable elapsed time string.
    *
    * @param {Float} elapsed elapsed seconds
    */
   elapsedTimeToString: function( value )
   {
      let T = Math.trunc( value );
      let ms = value - Math.floor( value );
      let sec = T % 60;
      let min = Math.trunc( ( T - sec ) / 60 ) % 60;
      let hours = Math.trunc( ( T - sec - min * 60 ) / 3600 );

      // short times below 1 second are represented in ms
      if ( hours == 0 && min == 0 && sec == 0 )
         return Math.trunc( ms * 1000 ) + " ms";

      if ( hours == 0 )
      {
         if ( min == 0 )
            // less than 1 minute is represented in simple seconds only with the given precision
            return format( "%02.0f s", sec );
         else
            // minutes are represented with fixed mm:ss (rounded)
            return format( "%02d:%02.0f", min, sec );
      }
      else
         // hour is represented as hh:mm:ss
         return format( "%02d:%02d:%02.0f", hours, min, sec );

   },

   /**
    * Returns the given size (in bytes) in a readable format string
    *
    * @param {*} _size size in bytes
    * @param {*} _padding the padding to be used
    * @return {*} the readable string
    */
   readableSize: function( _size, _padding )
   {
      let padding = _padding != undefined ? _padding : 12;
      let size = _size * 1.0;
      let Kb = 1024.0;
      let Mb = Kb * 1024.0;
      let Gb = Mb * 1024.0;
      let str;
      if ( size < Mb )
         str = format( "%.2f KiB", size / Kb );
      else if ( size < Gb )
         str = format( "%.2f MiB", size / Mb );
      else
         str = format( "%.2f GiB", size / Gb );
      return " ".repeat( Math.max( 0, padding - str.length ) ) + str;
   },

   /*
    * Returns a clean filter name.
    */
   cleanFilterName: function( str )
   {
      let sanitizeRegExp = new RegExp( "[^" + BPP.Format.KEYWORD_VALUE_CHARSET + "]", "gi" );
      let returnStr;
      try
      {
         returnStr = str.replace( sanitizeRegExp, '-' );
      }
      catch ( e )
      {
         console.warningln( "** Warning: cleanFilterName() raised an exception on string '" + str + "' with regexp '" + sanitizeRegExp + "'" );
         returnStr = str;
      }
      return returnStr;
   },

   /*
    * Returns true if this string is empty.
    */
   isEmptyString: function( str )
   {
      return str == undefined || str.length <= 0;
   },

   /*
    * Returns true if this string contains the specified substring.
    */
   stringHas: function( str, s )
   {
      return str.indexOf( s ) > -1;
   },

   /*
    * Add the given padding to a string
    */
   paddedStringNumber: function( str, padding )
   {
      let intPart = str.split( '.' );
      let P = Math.max( 0, padding - intPart[ 0 ].length );
      let Pad = " ".repeat( P );
      return Pad + str;
   },

   /**
    * Append a sequence of chars to a label to span the given length
    *
    * @param {*} label the main label aligned on the left
    * @param {*} N the total length to reach
    * @param {*} char the filler char
    * @return {*} the padded label
    */
   paddedLabel: function( label, N, char )
   {
      return label + ( char || "." ).repeat( Math.max( 0, N - label.length ) );
   },

   /**
    * Copy the astrometric solution from a source image to a target image.
    *
    * Only copies valid solutions that include spline-based world
    * transformations with distortion corrections.
    *
    * @param {ImageWindow} source the image window containing the astrometric solution to copy.
    * @param {ImageWindow} target the target image window the astrometric solution is copied to.
    */
   copyAstrometricSolution: function( source, target )
   {
      if ( source.mainView.hasProperty( "PCL:AstrometricSolution:SplineWorldTransformation" )
         || source.mainView.hasProperty( "AstrometricSolution:SplineWorldTransformation" ) )
         target.copyAstrometricSolution( source );
   },

   /**
    * Returns true iff the specified image \a window has a valid astrometric
    * solution (linear or spline-based).
    */
   hasAstrometricSolution: function( window )
   {
      return window.astrometricSolutionSummary().length > 0;
   },

   /**
    * Checks if the image has metadata for a spline-based world transformation
    * with distortion corrections.
    *
    * @param {*} source
    * @return {*}
    */
   hasSplineAstrometricSolutionMetadata: function( window )
   {
      return ( window.mainView.hasProperty( "PCL:AstrometricSolution:SplineWorldTransformation" )
         || window.mainView.hasProperty( "AstrometricSolution:SplineWorldTransformation" ) );
   },

   // ----------------------------------------------------------------------------
   // File Utils
   // ----------------------------------------------------------------------------

   /**
    * Creates a directory if it does not exist.
    * Returns the directory path.
    */
   existingDirectory: function( dir )
   {
      if ( !File.directoryExists( dir ) )
      {
         try
         {
            File.createDirectory( dir );
         }
         catch ( e )
         {
            // V8: File.createDirectory throws if an intermediate directory
            // already exists. Ignore "File exists" errors; re-throw others.
            if ( !File.directoryExists( dir ) )
               throw e;
         }
      }
      return dir;
   },

   getLastModifiedDate: function( files )
   {
      if ( files == undefined )
         return undefined;
      let singleFile = false;
      if ( typeof files == typeof "" )
      {
         files = [ files ];
         singleFile = true;
      }
      let result = [];
      let fileInfo = new FileInfo();
      for ( let i = 0; i < files.length; i++ )
      {
         let lmd = undefined;
         if ( files[ i ].length > 0 && File.exists( files[ i ] ) )
         {
            fileInfo.refresh( files[ i ] );
            lmd = fileInfo.lastModified.toISOString();
         }
         result.push( lmd );
      }
      return singleFile ? result[ 0 ] : result;
   },

   /**
    * Returns the image width, height.
    *
    * @param {*} filePath
    * @return {*}
    */
   getImageSize: function( filePath, inputHints )
   {
      try
      {
         let suffix = File.extractExtension( filePath ).toLowerCase();
         let format = new FileFormat( suffix, true /*toRead*/ , false /*toWrite*/ );
         if ( format.isNull )
            throw new Error( "No installed file format can read \'" + suffix + "\' files." );

         let file = new FileFormatInstance( format );
         if ( file.isNull )
            throw new Error( "Unable to instantiate file format: " + format.name );

         let description = file.open( filePath, inputHints || "" /*inputHints*/ );
         if ( description.length < 1 )
            throw new Error( "Unable to open file: " + filePath );
         let width = description[ 0 ].width;
         let height = description[ 0 ].height;
         file.close();

         return {
            width: width,
            height: height
         }

      }
      catch ( error )
      {
         // File could not be opened or read — return undefined to signal failure
         return undefined;
      }

   },

   keywords:
   {
      readFileInfos: function( filePath, inputHints, smartNamingOverride )
      {
         let ext = File.extractExtension( filePath ).toLowerCase();
         let format = new FileFormat( ext, true /*toRead*/ , false /*toWrite*/ );
         if ( format.isNull ) // shouldn't happen
            return {
               success: false,
               message: "No installed file format can read \'" + ext + "\' files."
            };
         let file = new FileFormatInstance( format );
         if ( file.isNull )
            return {
               success: false,
               message: "Unable to instantiate file format: " + format.name
            };

         let info = file.open( filePath, "verbosity 0 " + ( inputHints ? inputHints : "" ) ); // do not fill the console with useless messages
         if ( !info || info.length < 1 )
            return {
               success: false,
               message: "Unable to open input file: " + filePath
            };

         let result = {
            success: true,
            message: "Successfully read the image metadata"
         };

         /*
          * Initialize the result object containig all the image metadata.
          */

         // image type and geometry
         result.imageType = ImageType.Unknown;
         result.isMaster = null;
         result.size = {
            width: info[ 0 ].width,
            height: info[ 0 ].height
         };

         // image properties
         result.binning = null;
         result.filter = null;
         result.exposureTime = null;
         result.bayerpat = null;

         // overscan info
         result.overscan = new Overscan();
         result.preovsch = null;
         result.preovscw = null;

         // image solver parameters
         result.timeStart = null;
         result.timestamp = 0;
         result.observationDate = "";
         result.centerRA = null;
         result.centerDec = null;
         result.pixelSize = null;
         result.focalLength = null;

         result.keywords = [];

         /**
          * Defines the value of a metadata property in the returned object.
          *
          * @param {String} name - The name of the property
          * @param {*} value - The value of the property
          */
         function setProperty( name, value )
         {
            if ( value !== undefined && value !== null && !Number.isNaN( value ) && value !== "" )
               result[ name ] = value;
         }

         /**
          * Returns the image type from a keyword value.
          *
          * @param {String} value - The keyword value
          * @returns {ImageType} The image type
          */
         function imageTypeFromKeyword( value )
         {
            switch ( value.toLowerCase().replace( " ", "" ) )
            {
               case "bias":
               case "biasframe":
               case "masterbias":
                  return ImageType.Bias;
               case "dark":
               case "darkframe":
               case "masterdark":
               case "flatdark":
               case "darkflat":
                  return ImageType.Dark;
               case "flat":
               case "flatframe":
               case "flatfield":
               case "masterflat":
                  return ImageType.Flat;
               case "light":
               case "lightframe":
               case "scienceframe":
               case "science":
               case "masterlight":
                  return ImageType.Light;
               default:
                  return ImageType.Unknown;
            }
         }

         /**
          * Checks if the file is to be considered a master file from the IMAGETYP keyword's value.
          *
          * @param {String} value IMAGETYP keyword's value
          * @returns true if file is to be used as a master file
          */
         function isMasterFromKeyword( value )
         {
            return value.toLowerCase().indexOf( "master" ) >= 0;
         }

         /**
          * Extracts image metadata from an XISF property.
          *
          * @param {String} name - The XISF property identifier
          * @param {*} value - The XISF property value
          * @returns {void}
          */
         function getXISFProperty( name, value )
         {
            switch ( name )
            {
               case "PCL:Image:Type": // custom property to store the image type
                  switch ( value )
                  {
                     case ImageType.Bias:
                        setProperty( "imageType", ImageType.Bias );
                        setProperty( "isMaster", false );
                        break;
                     case ImageType.Dark:
                        setProperty( "imageType", ImageType.Dark );
                        setProperty( "isMaster", false );
                        break;
                     case ImageType.Flat:
                        setProperty( "imageType", ImageType.Flat );
                        setProperty( "isMaster", false );
                        break;
                     case ImageType.Light:
                     case ImageType.MasterLight: // light frames are never used as masters
                        setProperty( "imageType", ImageType.Light );
                        setProperty( "isMaster", false );
                        break;
                     case ImageType.MasterBias:
                        setProperty( "imageType", ImageType.Bias );
                        setProperty( "isMaster", true );
                        break;
                     case ImageType.MasterDark:
                        setProperty( "imageType", ImageType.Dark );
                        setProperty( "isMaster", true );
                        break;
                     case ImageType.MasterFlat:
                        setProperty( "imageType", ImageType.Flat );
                        setProperty( "isMaster", true );
                        break;
                  }
                  break;
               case "Observation:Center:RA":
                  setProperty( "centerRA", value );
                  break;
               case "Observation:Center:Dec":
                  setProperty( "centerDec", value );
                  break;
               case "Observation:Time:Start":
                  if ( value instanceof Date )
                  {
                     setProperty( "timestamp", value.getTime() );
                     setProperty( "observationDate", value.toISOString() );
                  }
                  break;
               case "Instrument:Sensor:XPixelSize":
                  setProperty( "pixelSize", value );
                  break;
               case "Instrument:Telescope:FocalLength":
                  setProperty( "focalLength", value * 1000 );
                  break;
               case "Instrument:ExposureTime":
               case "Instrument:FrameExposureTime": // in integrated masters
                  setProperty( "exposureTime", value );
                  break;
               case "Instrument:Camera:XBinning":
                  setProperty( "binning", value );
                  break;
               case "Instrument:Filter:Name":
                  setProperty( "filter", value );
                  break;
               case "PCL:CFASourcePattern":
                  setProperty( "bayerpat", value );
                  break;
            }
         }

         /**
          * Extracts image metadata from a FITS keyword.
          *
          * @param {String} name - The name of the FITS keyword
          * @param {String} value - The value of the FITS keyword
          * @returns {void}
          */
         function getFITSKeyword( name, value )
         {
            switch ( name )
            {
               case "IMAGETYP":
               {
                  let imageType = imageTypeFromKeyword( value );
                  let isMaster = isMasterFromKeyword( value );
                  setProperty( "imageType", imageType );
                  setProperty( "isMaster", isMaster );
               }
               break;
            case "XBINNING":
            case "CCDBINX":
            case "BINNING":
               setProperty( "binning", parseInt( value ) );
               break;
            case "FILTER":
            case "INSFLNAM":
               setProperty( "filter", value );
               break;
            case "EXPTIME":
            case "EXPOSURE":
               setProperty( "exposureTime", parseFloat( value ) );
               break;
            case "BAYERPAT":
               setProperty( "bayerpat", value );
               break;
            case "PREOVSCW":
               setProperty( "preovscw", parseFloat( value ) );
               break;
            case "PREOVSCH":
               setProperty( "preovsch", parseFloat( value ) );
               break;
            case "DATE-OBS": // observation time (UTC)// let's add the postfix Z if needed to ensure this is interpreted as an UTC date
            {
               let utcValue = value + ( ( value[ value.length - 1 ] == "Z" ) ? "" : "Z" );
               let d = new Date( utcValue );
               let timestamp = d.getTime();
               if ( isFinite( d.getTime() ) ) // if the ISO 8601 representation is valid
               {
                  setProperty( "timestamp", timestamp );
                  setProperty( "observationDate", d.toISOString() );
               }
            }
            break;
            case "RA": // right ascension of the center of the image
               setProperty( "centerRA", parseFloat( value ) );
               break;
            case "DEC": // declination of the center of the image
               setProperty( "centerDec", parseFloat( value ) );
               break;
            case "OBJCTRA": // right ascension of the center of the image
            {
               let angle = DMSangle.FromString( value, 0, 24 );
               if ( angle != null )
                  setProperty( "centerRA", 15 * angle.GetValue() );
            }
            break;
            case "OBJCTDEC": // declination of the center of the image
            {
               let angle = DMSangle.FromString( value, 0, 90 );
               if ( angle != null )
                  setProperty( "centerDec", angle.GetValue() );
            }
            break;
            case "XPIXSZ": // pixel size in micron, including binning
            {
               let parsedValue = parseFloat( value );
               if ( !isNaN( parsedValue ) && parsedValue > 0 )
                  setProperty( "pixelSize", parsedValue );
            }
            break;
            case "FOCALLEN": // focal length in mm, including binning
            {
               let parsedValue = parseFloat( value );
               if ( !isNaN( parsedValue ) && parsedValue > 0 )
                  setProperty( "focalLength", parsedValue );
            }
            break;
            default:
               // side effect: update the overscan parameters
               result.overscan.updateWithKeyword( name, value );
               break;
            }
         }

         /*
          * Get image metadata from the FITS header first.
          */
         let fitsKeywords = [];
         if ( format.canStoreKeywords )
         {
            result.keywords = file.keywords;
            // preprocess the FITS header keywords in order to ensure that some special keywords have precedence to others
            // this is currently valid for RA and DEC over OBJCTRA and OBJCTDEC
            let postponedKeywords = [];
            for ( let i = 0; i < result.keywords.length; ++i )
            {
               let name = result.keywords[ i ].name;
               if ( name == "HISTORY" )
                  continue;
               let value = result.keywords[ i ].strippedValue;

               // postpone the keywords RA and DEC to be processed later, to overwrite any OBJCTRA and OBJCTDEC values
               if ( name == "RA" || name == "DEC" )
               {
                  postponedKeywords.push(
                  {
                     name: name,
                     value: value
                  } );
               }
               else
               {
                  fitsKeywords.push(
                  {
                     name: name,
                     value: value
                  } );
               }
            }
            postponedKeywords.forEach( keyword =>
            {
               fitsKeywords.push( keyword );
            } );

            // now process the FITS header keywords
            for ( let i = 0; i < fitsKeywords.length; ++i )
            {
               let name = fitsKeywords[ i ].name;
               let value = fitsKeywords[ i ].value;
               getFITSKeyword( name, value );
            }
         }

         /*
          * Get image metadata from XISF properties.
          */
         getXISFProperty( "PCL:Image:Type", info[ 0 ].imageType );
         if ( format.canStoreImageProperties )
         {
            let propertyDescriptions = file.imageProperties;
            for ( let i = 0; i < propertyDescriptions.length; ++i )
            {
               let id = propertyDescriptions[ i ][ 0 ];
               if ( !id.startsWith( "PixInsight:" ) ) // performance improvement: ignore core private properties
                  getXISFProperty( id, file.readImageProperty( id ) );
            }
         }

         file.close();

         /*
          * Smart naming override.
          */
         if ( smartNamingOverride )
         {
            let keywords = fitsKeywords.reduce( ( keywords, keyword ) =>
            {
               keywords[ keyword.name ] = true;
               return keywords;
            },
            {} );
            [ "IMAGETYP", "FILTER", "INSFLNAM", "XBINNING", "BINNING", "CCDBINX", "EXPTIME", "EXPOSURE", "BAYERPAT" ].forEach( keyword =>
            {
               keywords[ keyword ] = true;
            } );
            let keywordsNames = Object.keys( keywords );
            for ( let i = 0; i < keywordsNames.length; ++i )
            {
               let name = keywordsNames[ i ];
               let value = WBPPUtils.smartNaming.getCustomKeyValueFromPath( name, filePath );
               if ( value != undefined )
                  getFITSKeyword( name, value );
            }
         }

         return result;
      },

      readFileKeyword: function( filePath, keyword )
      {
         let result = this.readFileInfos( filePath );
         if ( result.success )
         {
            let upKey = keyword.toUpperCase();
            for ( let i = 0; i < result.keywords.length; ++i )
               if ( result.keywords[ i ].name.toUpperCase() == upKey )
                  return result.keywords[ i ].value;
         }
         return undefined;
      },
   },

   /**
    * Returns an existing and unique file path given the desired file name and the output folder.
    * In order not to overwrite existing files, incremental indices are appended to the file name
    * until uniqueness is guaranteed.
    *
    * @param {String} outputFolder the folder containing the file name, must be non empty.
    * @param {String} fileName the desired file name including the file extension.
    */
   existingAndUniqueFileName: function( outputFolder, fileName )
   {
      if ( !File.directoryExists( outputFolder ) )
      {
         try
         {
            File.createDirectory( outputFolder );
         }
         catch ( e )
         {
            if ( !File.directoryExists( outputFolder ) )
               throw e;
         }
      }
      let filePath = outputFolder + "/" + fileName;
      let uniqueFilePath;
      let j = 0;
      let postFix = "";
      do {
         uniqueFilePath = File.appendToName( filePath, postFix );
         j++;
         postFix = "_(" + j + ")";
      }
      while ( File.exists( uniqueFilePath ) );
      return uniqueFilePath;
   },

   // ----------------------------------------------------------------------------
   // Smart Naming Helpers
   // ----------------------------------------------------------------------------

   smartNaming:
   {
      lastMatching: function( text, regexp )
      {
         let matches = text.match( regexp )
         if ( matches != null && matches.length > 0 )
         {
            return matches[ matches.length - 1 ];
         }
         return undefined;
      },

      /*
       * Extract the master property from the file Path.
       *
       * fileName must contain the "master" string in its name in order to be recognized
       * as a master file from SmartNaming.
       *
       * NOTE: The check is case-insensitive
       */
      isMasterFromPath: function( filePath )
      {
         let regexp = /(MASTER)/gi;
         return this.lastMatching( filePath, regexp ) != undefined;
      },

      /*
       * Extract the image type from the last matching pattern occurrence in its
       * filePath.
       *
       * filePath must contain one pr more of BIAS, DARK, FLAT, LIGHT.
       * The last of the sequence will be taken. It is useful to check the
       * whole path since instead of renaming single files it's possible to put all
       * light files into an enclosing folder with the word "lights" in the name.
       *
       * NOTE: Negative look behind is not supported in JS so the first char
       * before the keywords is matched and removed in the switch.
       */
      getImageTypeFromPath: function( filePath )
      {
         let regexp = /(?![a-z0-9]).{0,1}(BIAS|DARK|DARKS|FLAT|FLATS|LIGHT|LIGHTS)(?![a-z0-9])/gi;
         let fileType = this.lastMatching( filePath, regexp );
         if ( fileType )
            switch ( fileType.substr( 1 ).toUpperCase() )
            {
               case 'BIAS':
                  return ImageType.Bias;
               case 'DARK':
               case 'DARKS':
                  return ImageType.Dark;
               case 'FLAT':
               case 'FLATS':
                  return ImageType.Flat;
               case 'LIGHT':
               case 'LIGHTS':
                  return ImageType.Light;
            }
         return ImageType.Unknown;
      },

      sanitizeKeywordValue: function( value )
      {
         let sanitizeRegExp = new RegExp( "[^" + BPP.Format.KEYWORD_VALUE_CHARSET + "]", "gi" );
         return value.replace( sanitizeRegExp, '-' );
      },

      /*
       * Extract the exposure time from the last matching pattern occurrence in its filePath.
       * Exposure can be specified by means of explicit keywords (EXPTIME, EXPOSURE) or
       * numeric values followed by time suffixes (s, sec, _secs).
       */
      getExposureTimeFromPath: function( filePath )
      {
         // match the format EXPTIME_10.0 or EXPOSURE_2
         let regexp = /(EXPTIME|EXPOSURE)(_|-| )[0-9]+(\.[0-9]*)?/gi;
         let match = this.lastMatching( filePath, regexp );
         if ( match )
         {
            let sanitizedStrValue = match.replace( /(EXPTIME|EXPOSURE)(_|-| )/gi, '' );
            let value = Number( sanitizedStrValue );
            return isNaN( value ) ? 0 : value;
         }
         // find any number followed by 's' or 'sec' ore '_secs' like 2s, 2.1_secs or 2.2sec
         let postfixes = [ 's', 'sec', '_secs' ];
         regexp = /[0-9]+(\.[0-9]*)?(?=(s|sec|_secs)[^a-zA-Z0-9])/gi;
         let matches = regexp.exec( filePath );
         if ( matches !== null )
         {
            let sanitizedStr = matches[ 0 ];
            postfixes.forEach( postfix =>
            {
               sanitizedStr = sanitizedStr.replace( postfix, '' );
            } );
            let value = Number( sanitizedStr );
            return isNaN( value ) ? 0 : value;
         }
         return 0;
      },

      /*
       * Extract the binning from the last matching pattern occurrence in its filePath.
       */
      getBinningFromPath: function( filePath )
      {
         let regexp = /(XBINNING|CCDBINX|BINNING)(_|-| )[0-9]+/gi;
         let match = this.lastMatching( filePath, regexp );
         if ( match )
         {
            let sanitizedStrValue = match.replace( /(XBINNING|CCDBINX|BINNING)(_|-| )/gi, '' );
            let value = Number( sanitizedStrValue );
            return isNaN( value ) ? 1 : value;
         }
         return 1;
      },

      /*
       * Extract the filter name from the last matching pattern occurrence in its filePath.
       * Possible valid combinations within the path are:
       * - FILTER NebulaBooster
       * - FILTER-Ha
       * - INSFLNAM_L
       */
      getFilterFromPath: function( filePath )
      {
         let regexp = /(FILTER|INSFLNAM)(_|-| )[- a-zA-Z0-9]+/gi;
         let match = this.lastMatching( filePath, regexp );
         if ( match )
            return match.replace( /(FILTER|INSFLNAM)(_|-| )/gi, '' );
         return undefined;
      },

      /**
       * Extracts a custom key-value pair from a file path.
       *
       * This function searches for the last occurrence of a specified key in the file path
       * and extracts its associated value. The key-value pattern must follow these rules:
       * - The key must be preceded by a non-alphanumeric character
       * - The key and value must be separated by either a hyphen (-), underscore (_), or space
       * - The value can only contain characters defined in BPP.Format.KEYWORD_VALUE_CHARSET
       *
       * @param {string} key - The key to search for in the file path
       * @param {string} filePath - The complete file path to search within
       * @returns {string|undefined} The extracted value associated with the key, or undefined if not found
       */
      getCustomKeyValueFromPath: function( key, filePath )
      {
         // Remove the file extension to avoid false matches
         let extension = File.extractExtension( filePath );
         let sanitizedFilePath = filePath.slice( 0, -extension.length );

         // Create a regex pattern to find the key-value pair
         // The pattern looks for a non-alphanumeric character, followed by the key,
         // followed by a separator (_, -, or space), followed by valid characters
         let regexp = new RegExp( "[^a-zA-Z0-9](" + key + ")(_|-| )[" + BPP.Format.KEYWORD_VALUE_CHARSET + "]+", "gi" );
         let match = this.lastMatching( sanitizedFilePath, regexp );

         if ( match )
         {
            // Remove the key and separator from the match
            let subsRegExp = new RegExp( "[^a-zA-Z0-9](" + key + ")(_|-| )", "gi" );
            // Replace any invalid characters with hyphens
            let sanitizeRegExp = new RegExp( "[^" + BPP.Format.KEYWORD_VALUE_CHARSET + "]", "gi" );
            return match.replace( subsRegExp, '' ).replace( sanitizeRegExp, "-" );
         }
         return undefined;
      },
   },

   computeSTFAutoStretch: function( view, descriptor = {}, c0Add = 0, mAdd = 0 )
   {
      const n = view.image.isColor ? 3 : 1;
      let median = [];
      let mad = [];
      if ( descriptor.median !== undefined && descriptor.mad !== undefined && n == 1 )
      {
         median = [ descriptor.median ];
         mad = [ descriptor.mad ];
      }
      else if ( descriptor.rgbMad !== undefined && descriptor.rgbMedian !== undefined )
      {
         median = descriptor.rgbMedian;
         mad = descriptor.rgbMad;
      }
      else
      {
         let medianValues = view.computeOrFetchProperty( "Median" );
         let madValues = view.computeOrFetchProperty( "MAD" );
         for ( let c = 0; c < n; ++c )
         {
            median[c] = medianValues[c];
            mad[c] = 1.4826*madValues[c];
         }
         // store the arrays in the descriptor for a future reuse
         descriptor.rgbMedian = median;
         descriptor.rgbMad = mad;
      }
      // Ensure that the median is never negative.
      median = median.map( ( item ) => Math.max( 0.00001, item ) );

      let stf = view.image.computeAutoStretch( median, mad, -2.8/*clip*/, 0.25/*targetBkg*/, false/*linkedRGB*/ );
      for ( let i = 0; i < stf.length; ++i )
      {
         stf[i][0] = Math.range( stf[i][0] + mAdd, 0, 1 );
         stf[i][1] += c0Add;
      }
      return stf;
   },

   // ----------------------------------------------------------------------------
   // UTF-8 Base64 encoding helpers
   // ----------------------------------------------------------------------------

   toBase64UTF8: function( string )
   {
      return ByteArray.stringToUTF8( string ).toBase64();
   },

   fromBase64UTF8: function( base64String )
   {
      return ByteArray.fromBase64( base64String ).utf8ToString();
   },

   // ----------------------------------------------------------------------------
   // Extensions to the Parameters object
   // ----------------------------------------------------------------------------

   JSONParameters:
   {
      clear: function()
      {
         this.data = {};
      },
      set: function( key, object )
      {
         this.data[ key ] = object;
      },
      setIndexed: function( key, index, object )
      {
         if ( this.data[ key ] == undefined )
            this.data[ key ] = [];
         this.data[ key ][ index ] = object;
      },
      fromJSONtest: function( json )
      {
         let data = JSON.parse( json );
         if ( data == undefined )
            return;
         this.data = {};
         Object.keys( data.data ).forEach( key =>
         {
            this.data[ key ] = data.data[ key ];
         } );
      },
      has: function( key )
      {
         return this.data[ key ] != undefined
      },
      hasIndexed: function( key, index )
      {
         return this.data[ key ] != undefined && Array.isArray( this.data[ key ] ) && this.data[ key ].length > index;
      },
      getBoolean: function( key )
      {
         return !!this.data[ key ];
      },
      getInteger: function( key )
      {
         return parseInt( this.data[ key ] );
      },
      getReal: function( key )
      {
         return parseFloat( this.data[ key ] );
      },
      getString: function( key )
      {
         return this.data[ key ];
      },
      getBooleanIndexed: function( key, index )
      {
         return !!this.data[ key ][ index ];
      },
      getIntegerIndexed: function( key, index )
      {
         return parseInt( this.data[ key ][ index ] );
      },
      getRealIndexed: function( key, index )
      {
         return parseFloat( this.data[ key ][ index ] );
      },
      getStringIndexed: function( key, index )
      {
         return this.data[ key ][ index ];
      },
      getUIntIndexed: function( key, index )
      {
         return parseInt( this.data[ key ][ index ] );
      }
   },
   parameters:
   {
      indexedId: function( id, index )
      {
         return id + '_' + ( index + 1 ).toString(); // make indexes one-based
      },
      hasIndexed: function( id, index )
      {
         return Parameters.has( this.indexedId( id, index ) );
      },
      getBooleanIndexed: function( id, index )
      {
         return Parameters.getBoolean( this.indexedId( id, index ) );
      },
      getIntegerIndexed: function( id, index )
      {
         return Parameters.getInteger( this.indexedId( id, index ) );
      },
      getRealIndexed: function( id, index )
      {
         return Parameters.getReal( this.indexedId( id, index ) );
      },
      getStringIndexed: function( id, index )
      {
         return Parameters.getString( this.indexedId( id, index ) );
      },
      getUIntIndexed: function( id, index )
      {
         return Parameters.getUInt( this.indexedId( id, index ) );
      },
      getStringList: function( id )
      {
         let list = new Array();
         if ( Parameters.has( id ) )
         {
            let s = Parameters.getString( id );
            list = s.split( ':' );
            for ( let i = 0; i < list.length; ++i )
               list[ i ] = list[ i ].trim();
         }
         return list;
      },
      setIndexed: function( id, index, value )
      {
         return Parameters.set( this.indexedId( id, index ), value );
      },
   },
   factory:
   {
      CPTreeBox: function( parent )
      {
         let treeBox = new TreeBox( parent );
         treeBox.rootDecoration = false;
         treeBox.headerVisible = true;
         treeBox.alternateRowColor = true;
         treeBox.numberOfColumns = 1;
         return treeBox;
      },
      CPHeader: function( parent, title )
      {
         let label = new Label( parent );
         label.text = "<b>" + title + "</b>";
         label.margin = 8;
         label.spacing = 8;
         label.useRichText = true;
         return label;
      },
      CPMasterSelectionControl: function( parent, title )
      {
         let control = new Control( parent );
         let label = new Label( control );
         label.useRichText = true;
         label.text = title;
         label.setFixedWidth( 34 );
         label.textAlignment = TextAlignment.VertCenter;
         let combo = new ComboBox( control );
         combo.setVariableWidth();
         control.sizer = new HorizontalSizer;
         control.sizer.add( label );
         control.sizer.add( combo );
         return combo;
      }
   },

   /**
    * Validates a JavaScript expression without producing console warnings.
    * Uses the Function constructor to create an isolated execution context
    * where variables are explicit function parameters, avoiding "reference to
    * undefined property" warnings that occur with eval().
    *
    * @param {string} expression - The JavaScript expression to validate
    * @param {Object|Array} variables - Either:
    *                             - Object mapping variable names to test values
    *                               Example: { "WHMwhm": 2.5, "SNR": 150, "Median": 0.5 }
    *                             - Array of variable definitions with 'name' property
    *                               Example: [{ name: "FWHM", key: "FWHM" }, ...]
    *                               In this case, the expression is normalized and
    *                               random test values (1-11) are generated automatically.
    * @param {Object} options - Optional settings:
    *                           - requireNumeric: boolean (default true) - require numeric result
    *                           - allowNaN: boolean (default false) - allow NaN as valid result
    *                           - allowInfinity: boolean (default false) - allow Infinity as valid result
    * @returns {Object} Result object:
    *                   - valid: boolean - true if expression is valid
    *                   - error: string|null - error message if invalid, null otherwise
    *                   - result: any - the computed result if valid, undefined otherwise
    */
   validateExpression: ( expression, variables, options ) =>
   {
      // Default options
      options = options
         ||
         {};
      let requireNumeric = !options.hasOwnProperty( 'requireNumeric' ) || options.requireNumeric; // default true
      let allowNaN = options.hasOwnProperty( 'allowNaN' ) && options.allowNaN; // default false
      let allowInfinity = options.hasOwnProperty( 'allowInfinity' ) && options.allowInfinity; // default false

      // Result object
      let validationResult = {
         valid: true,
         error: null,
         result: undefined
      };

      // Check for empty expression
      if ( !expression || expression.trim().length === 0 )
      {
         validationResult.valid = false;
         validationResult.error = "Empty expression";
         return validationResult;
      }

      // Check for valid variables object or array
      if ( !variables || typeof variables !== 'object' )
      {
         validationResult.valid = false;
         validationResult.error = "Invalid variables object";
         return validationResult;
      }

      // If variables is an array of definitions, normalize expression and generate random values
      if ( Array.isArray( variables ) )
      {
         expression = WBPPUtils.normalizeFormulaVariables( expression, variables );
         let variableDefinitions = variables;
         variables = {};
         for ( let i = 0; i < variableDefinitions.length; i++ )
         {
            let variable = variableDefinitions[ i ];
            variables[ variable.name ] = 1 + Math.random() * 10;
         }
      }

      try
      {
         // Build parameter names and values arrays
         let paramNames = Object.keys( variables );
         let paramValues = paramNames.map( name => variables[ name ] );

         // Create function with explicit parameters as a comma-separated string
         // This avoids "reference to undefined property" warnings because
         // all variables are function parameters, not global property lookups
         // Note: new Function accepts parameter names as a single comma-separated string
         let paramString = paramNames.join( ", " );
         let fn = new Function( paramString, "return (" + expression + ")" );

         // Execute the function with the provided values
         let result = fn.apply( null, paramValues );

         // Store the result
         validationResult.result = result;

         // Validate the result type if required
         if ( requireNumeric )
         {
            if ( typeof result !== "number" )
            {
               validationResult.valid = false;
               validationResult.error = "Non-numeric result: " + ( typeof result );
               return validationResult;
            }

            if ( !allowNaN && isNaN( result ) )
            {
               validationResult.valid = false;
               validationResult.error = "Result is NaN (Not a Number)";
               return validationResult;
            }

            if ( !allowInfinity && !isFinite( result ) )
            {
               validationResult.valid = false;
               validationResult.error = "Result is Infinity";
               return validationResult;
            }
         }
      }
      catch ( e )
      {
         validationResult.valid = false;
         validationResult.error = e.toString();
      }

      return validationResult;
   },

   /**
    * Evaluates a JavaScript expression with the given variables.
    * Uses the Function constructor to avoid console warnings.
    * This is the execution counterpart of validateExpression().
    *
    * @param {string} expression - The JavaScript expression to evaluate
    * @param {Object} variables - Object mapping variable names to actual values
    * @returns {any} The computed result, or null if evaluation fails
    */
   evaluateExpression: ( expression, variables ) =>
   {
      if ( !expression || expression.trim().length === 0 || !variables )
         return null;

      try
      {
         let paramNames = Object.keys( variables );
         let paramValues = paramNames.map( name => variables[ name ] );

         // Note: new Function accepts parameter names as a single comma-separated string
         let paramString = paramNames.join( ", " );
         let fn = new Function( paramString, "return (" + expression + ")" );
         let result = fn.apply( null, paramValues );

         return result;
      }
      catch ( e )
      {
         // Evaluation failed silently
         return null;
      }
   },

   /**
    * Normalizes metric variable names in a formula expression.
    * Variable names are matched case-insensitively and replaced with their
    * canonical form (the 'name' property from the variable definition).
    * Other parts of the formula (like Math.log) are preserved as-is.
    *
    * @param {string} expression - The formula expression to normalize
    * @param {Array} variables - Array of variable definitions with 'name' property
    *                            (e.g., CustomFormulaVariables from BPP-FrameGroup.js)
    * @returns {string} Formula with normalized metric variable names
    */
   normalizeFormulaVariables: ( expression, variables ) =>
   {
      let result = expression;
      for ( let i = 0; i < variables.length; i++ )
      {
         let variable = variables[ i ];
         // Create a case-insensitive regex with word boundaries to match the variable name
         // Use a replacement function to skip matches preceded by a dot (property access)
         let regex = new RegExp( "(^|[^.])\\b(" + variable.name + ")\\b", "gi" );
         result = result.replace( regex, function( match, prefix, varName )
         {
            return prefix + variable.name;
         } );
      }
      return result;
   }
} );

var WBPPUtils = ( function()
{
   // Crea un oggetto con tutti i metodi helper
   let utils = helperFunctions();

   // Copia tutte le funzioni direttamente nell'oggetto WBPPUtils
   let result = {};
   for ( let key in utils )
   {
      result[ key ] = utils[ key ];
   }

   return result;
} )();

/*
 * Secure directory removal routine.
 */
function removeDirectoryAndContent( dirPath )
{
   function removeDirectory_recursive( dirPath, baseDir )
   {
      if ( dirPath.indexOf( ".." ) >= 0 )
         throw new Error( "removeDirectory(): Attempt to climb up the filesystem." );
      if ( dirPath.indexOf( baseDir ) != 0 )
         throw new Error( "removeDirectory(): Attempt to redirect outside the base directory." );
      if ( !File.directoryExists( dirPath ) )
         throw new Error( "removeDirectory(): Attempt to remove a nonexistent directory." );

      let currentDir = dirPath;
      if ( currentDir[ currentDir.length - 1 ] != '/' )
         currentDir += '/';

      let find = new FileFind;
      if ( find.begin( currentDir + "*" ) )
         do {
            let itemPath = currentDir + find.name;
            if ( find.isDirectory )
            {
               if ( find.name != "." && find.name != ".." )
               {
                  removeDirectory_recursive( itemPath, baseDir );
                  File.removeDirectory( itemPath );
               }
            }
            else
            {
               File.remove( itemPath );
            }
         }
         while ( find.next() );
   }

   if ( dirPath.indexOf( '/' ) != 0 )
      throw new Error( "removeDirectory(): Relative directory." );
   if ( !File.directoryExists( dirPath ) )
      throw new Error( "removeDirectory(): Nonexistent directory." );

   // Remove all files and subdirectories recursively
   removeDirectory_recursive( dirPath, dirPath );

   File.removeDirectory( dirPath );
}

/*
 * FileList
 *
 * Recursively search a directory tree for all existing files with the
 * specified file extensions.
 */
var FileList = class
{

   constructor( dirPath, extensions, verbose )
   {
      this.baseDirectory = "";
      this.files = [];
      this.index = [];

      if ( dirPath != undefined )
         this.regenerate( dirPath, extensions, verbose );

      if ( verbose )
      {
         console.writeln( "<end><cbr>" + this.files.length + " file(s) found:" );
         for ( let i = 0; i < this.files.length; ++i )
            console.writeln( "<raw>" + this.files[ i ] + "</raw>" );
      }
   }

   /*
    * Regenerate this file list for the specified base directory and file
    * extensions.
    */
   regenerate( dirPath, extensions, verbose )
   {
      // Security check: Do not allow climbing up a directory tree.
      if ( dirPath.indexOf( ".." ) >= 0 )
         throw new Error( "FileList: Attempt to redirect outside the base directory: " + dirPath );

      // The base directory is the root of our search tree.
      this.baseDirectory = File.fullPath( dirPath );
      if ( this.baseDirectory.length == 0 )
         throw new Error( "FileList: No base directory has been specified." );

      // The specified directory can optionally end with a separator.
      if ( this.baseDirectory[ this.baseDirectory.length - 1 ] == '/' )
         this.baseDirectory = this.baseDirectory.slice( 0, -1 );

      // Security check: Do not try to search on a nonexisting directory.
      if ( !File.directoryExists( this.baseDirectory ) )
         throw new Error( "FileList: Attempt to search a nonexistent directory: " + this.baseDirectory );

      // If no extensions have been specified we'll look for all existing files.
      if ( extensions == undefined || extensions == null || extensions.length == 0 )
         extensions = [ '' ];

      if ( verbose )
      {
         console.writeln( "<end><cbr><br>==> Finding files from base directory:" );
         console.writeln( "<raw>" + this.baseDirectory + "</raw>" );
      }

      // Find all files with the required extensions in our base tree recursively.
      this.files = [];
      for ( let i = 0; i < extensions.length; ++i )
         this.files = this.files.concat( File.searchDirectory( this.baseDirectory + "/*" + extensions[ i ], true /*recursive*/ ) );
   }
}

function imageIdFromFileName( filePath )
{
   let id = "";
   let fn = filePath.split( '/' ).pop().trim(); // Extracts the file name from the path and trims it
   let u = false;

   for ( let ch of fn )
   {
      if ( ( ch >= 'a' && ch <= 'z' ) || ( ch >= 'A' && ch <= 'Z' ) || ( ch >= '0' && ch <= '9' ) )
      {
         id += ch;
         u = false;
      }
      else if ( ch === '_' || !u )
      {
         id += '_';
         u = true;
      }
   }

   if ( id.length > 0 && id[ 0 ] >= '0' && id[ 0 ] <= '9' )
      id = '_' + id;

   return id;
}

// ----------------------------------------------------------------------------
// EOF BPP-Helper.js - Released 2026-05-10T11:05:00Z
