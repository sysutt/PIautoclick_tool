// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Overscan.js - Released 2026-05-10T11:05:00Z
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
 * Overscan region constructor
 *
 */
var OverscanRegions = class
{
   constructor()
   {
      this.enabled = false; // whether to apply this overscan correction
      this.sourceRect = new Rect( 0 ); // source overscan region
      this.targetRect = new Rect( 0 ); // image region to be corrected
   }

   isValid()
   {
      if ( !this.enabled )
         return true;
      if ( !this.sourceRect.isNormal || !this.targetRect.isNormal )
         return false;
      if ( this.sourceRect.x0 < 0 || this.sourceRect.y0 < 0
         || this.targetRect.x0 < 0 || this.targetRect.y0 < 0 )
         return false;
      return true;
   }
}

// ----------------------------------------------------------------------------

/**
 * Overscan object constructor
 *
 */
var Overscan = class
{
   constructor()
   {
      this.enabled = false; // whether overscan correction is globally enabled

      this.overscan = new Array; // four overscan source and target regions
      this.overscan.push( new OverscanRegions );
      this.overscan.push( new OverscanRegions );
      this.overscan.push( new OverscanRegions );
      this.overscan.push( new OverscanRegions );

      this.imageRect = new Rect( 0 ); // image region (i.e. the cropping rectangle)
   }

   isValid()
   {
      if ( !this.enabled )
         return true;
      for ( let i = 0; i < 4; ++i )
         if ( !this.overscan[ i ].isValid() )
            return false;
      if ( !this.imageRect.isNormal )
         return false;
      if ( this.imageRect.x0 < 0 || this.imageRect.y0 < 0 )
         return false;
      return true;
   }

   hasOverscanRegions()
   {
      for ( let i = 0; i < 4; ++i )
         if ( this.overscan[ i ].enabled )
            return true;
      return false;
   }

   reset()
   {
      this.enabled = false;
      for ( let i = 0; i < 4; ++i )
         this.overscan[ i ].enabled = false;
   }

   updateWithKeyword( key, value )
   {
      let updateRect = function( rect, str, value )
      {
         switch ( str )
         {
            case "X0":
               rect.x0 = value;
               break;
            case "Y0":
               rect.y0 = value;
               break;
            case "X1":
               rect.x1 = value;
               break;
            case "Y1":
               rect.y1 = value;
               break;
         }
      };

      // quickly check of the keyword format
      if ( key.length != 7 )
         return;
      if ( key[ 0 ] != 'O' || key[ 1 ] != 'S' )
         return;
      if ( key[ 4 ] < '0' || key[ 4 ] > '3' )
         return;
      if ( key[ 5 ] != 'X' && key[ 5 ] != 'Y' )
         return;
      let intValue;
      let indx;
      let coord = key.substring( 5, 7 );
      try
      {
         intValue = parseInt( value );
         indx = parseInt( key.substring( 4, 5 ) );
      }
      catch ( _ )
      {}
      if ( intValue == undefined || indx == undefined )
         return;

      switch ( key.substring( 0, 4 ) )
      {
         case "OSIR": // image region
            updateRect( this.imageRect, coord, intValue );
            this.enabled = true;
            break;
         case "OSSR": // source region
            updateRect( this.overscan[ indx ].sourceRect, coord, intValue );
            this.overscan[ indx ].enabled = true;
            break;
         case "OSTR": // target region
            updateRect( this.overscan[ indx ].targetRect, coord, intValue );
            this.overscan[ indx ].enabled = true;
            break;
      }
   }

   copyFrom( source )
   {
      if ( source == undefined )
         return;
      this.enabled = source.enabled;
      this.imageRect = new Rect( source.imageRect );
      for ( let i = 0; i < 4; ++i )
      {
         this.overscan[ i ].enabled = source.overscan[ i ].enabled;
         this.overscan[ i ].sourceRect = new Rect( source.overscan[ i ].sourceRect );
         this.overscan[ i ].targetRect = new Rect( source.overscan[ i ].targetRect );
      }
   }

   toString()
   {
      let rectToTooltip = function( R )
      {
         return "  x0: " + R.x0 + "<br/>"
            + "  y0: " + R.y0 + "<br/>"
            + "  x1: " + R.x1 + "<br/>"
            + "  y1: " + R.y1 + "<br/>";
      };

      let str = "<p><b>Image region</b><br/>" + rectToTooltip( this.imageRect );
      for ( let i = 0; i < 4; ++i )
         if ( this.overscan[ i ].enabled )
            str += "<br/>Region #" + i + ":<br/>"
            + "[source rect]<br/>" + rectToTooltip( this.overscan[ i ].sourceRect )
            + "[target rect]<br/>" + rectToTooltip( this.overscan[ i ].targetRect );
      str += "</p>";
      return str;
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-Overscan.js - Released 2026-05-10T11:05:00Z
