// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Graph.js - Released 2026-05-10T11:05:00Z
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

function GraphGenerator( parent )
{
   // The parent control
   this.parent = parent;

   this.newFont = function( ptSize )
   {
      return new Font( "DejaVu Sans Mono", ptSize ? ptSize : 8 );
   };

   // The graph parameters
   {
      let boxFont = this.newFont();
      this.rowHeight = this.parent.logicalPixelsToPhysical( 80 );
      this.colWidth = this.parent.logicalPixelsToPhysical( 130 );
      this.boxSizeX = boxFont.width( "XCALIBRATED LightX" );
      this.boxSizeY = boxFont.lineSpacing * 5;
      this.opSize = this.parent.logicalPixelsToPhysical( 30 );
      this.roundRectRadius = this.parent.logicalPixelsToPhysical( 10 );
      this.originX0 = this.parent.logicalPixelsToPhysical( 96 ); // to center the graph within parent
      this.originY0 = this.parent.logicalPixelsToPhysical( 64 ); // ...
      this.x0 = this.originX0;
      this.y0 = this.originY0;
   }

   // The graphics context
   this.graphics = new Graphics();
   this.graphics.antialiasing = true;
   this.graphics.smoothInterpolation = true;
   this.graphics.textAntialiasing = true;
   this.ongoing = false;

   /**
    * This function draws a graph depicting the flow corresponding to the
    * provided parameters.
    *
    * @param {*} bias optional, the master bias name
    * @param {*} dark optional, the master dark name
    * @param {*} flat optional, the master flat name
    * @param {*} light the master light name
    * @returns A Rect object with the boundary coordinates of the generated
    * drawing.
    */
   this.generateGraph = ( viewport, bias, dark, flat, light, darkIsOptimized ) =>
   {
      let nodes = {};

      // false only when bias is provided but dark is not
      let darkIsCalibrated = !bias || ( bias && dark );
      // darkIsOptimized can be true only if dark is provided
      darkIsOptimized = darkIsOptimized && dark;

      // determine the location of the origin
      if ( ( dark && darkIsOptimized ) || ( bias && dark && darkIsCalibrated ) )
      {
         this.x0 = this.originX0;
         this.y0 = this.originY0;
      }
      else
      {
         this.x0 = this.originX0;
         this.y0 = this.originY0 - this.rowHeight;
      }

      // determine the relative placement of all boxes

      // BIAS position
      nodes.biasX = this.colWidth;
      nodes.biasY = this.rowHeight;

      // DARK box position
      if ( bias )
      {
         if ( darkIsCalibrated )
         {
            nodes.darkX = 0;
            nodes.darkY = 0;
         }
         else
         {
            if ( darkIsOptimized )
            {
               nodes.darkX = this.colWidth * 2;
               nodes.darkY = 0;
            }
            else
            {
               nodes.darkX = this.colWidth * 2;
               nodes.darkY = this.rowHeight;
            }
         }
      }
      else
      {
         if ( darkIsOptimized )
         {
            nodes.darkX = this.colWidth;
            nodes.darkY = 0;
         }
         else
         {
            nodes.darkX = this.colWidth;
            nodes.darkY = this.rowHeight;
         }
      }
      if ( darkIsOptimized )
      {
         nodes.optX = nodes.darkX;
         nodes.optY = nodes.darkY + this.rowHeight;
      }
      else
      {
         nodes.optX = nodes.darkX;
         nodes.optY = nodes.darkY;
      }

      // FLAT box position
      if ( !bias && !dark )
      {
         nodes.flatX = this.colWidth;
         nodes.flatY = this.rowHeight;
      }
      else if ( bias && dark )
      {
         nodes.flatX = this.colWidth * 3;
         nodes.flatY = this.rowHeight;
      }
      else
      {
         nodes.flatX = this.colWidth * 2;
         nodes.flatY = this.rowHeight;
      }

      // Light box Position
      nodes.lightX = 0;
      nodes.lightY = nodes.flatY + this.rowHeight;

      // --------------------------
      // create operators positions
      // --------------------------
      // dark calibration
      if ( darkIsCalibrated )
      {
         nodes.darkCalX = nodes.biasX;
         nodes.darkCalY = nodes.darkY;
      }
      else
      {
         nodes.darkCalX = nodes.darkX;
         nodes.darkCalY = nodes.darkY;
      }

      // bias subtraction
      nodes.biasSubX = nodes.lightX + ( bias ? this.colWidth : 0 );
      nodes.biasSubY = nodes.lightY;

      // dark subtraction
      nodes.darkSubX = nodes.biasSubX + ( dark ? this.colWidth : 0 );
      nodes.darkSubY = nodes.biasSubY;

      // flat division
      nodes.flatDivX = nodes.darkSubX + ( flat ? this.colWidth : 0 );
      nodes.flatDivY = nodes.darkSubY;

      // Master Light box Position
      nodes.masterLightX = nodes.flatDivX + this.colWidth;
      nodes.masterLightY = nodes.lightY;

      // dark optimization
      if ( darkIsOptimized )
      {
         if ( darkIsCalibrated && bias )
         {
            nodes.darkOptX = nodes.biasX + this.colWidth;
            nodes.darkOptY = nodes.biasY;
         }
         else
         {
            nodes.darkOptX = nodes.darkX;
            nodes.darkOptY = nodes.darkY + this.rowHeight;
         }
      }
      else
      {
         nodes.darkOptX = nodes.darkSubX;
         nodes.darkOptY = nodes.darkSubY;
      }

      // draw the diagram

      this.rect = new Rect( 0 );

      if ( !this.ongoing )
      {
         this.ongoing = true;
         this.graphics.begin( viewport );
         this.graphics.antialiasing = true;
         this.graphics.transparentBackground = true;

         // draw the dark flow
         this.drawFlow( nodes, bias, dark, flat, light, darkIsCalibrated );
         this.drawNodes( nodes, bias, dark, flat, light, darkIsCalibrated, darkIsOptimized );

         this.ongoing = false;
         this.graphics.end();
      }

      return this.rect;
   };

   this.drawFlow = ( nodes, bias, dark, flat, light, darkIsCalibrated ) =>
   {
      if ( light && light.masterFrame )
         return;

      // dark - bias subtraction
      if ( dark )
      {
         this.myDrawLine( nodes.darkX, nodes.darkY, nodes.darkCalX, nodes.darkCalY );
         if ( darkIsCalibrated )
            this.myDrawLine( nodes.biasX, nodes.biasY, nodes.darkCalX, nodes.darkCalY );
         this.myDrawLine( nodes.darkCalX, nodes.darkCalY, nodes.darkOptX, nodes.darkCalY );
         this.myDrawLine( nodes.darkOptX, nodes.darkCalY, nodes.darkOptX, nodes.darkOptY );
      }

      // bias subtraction
      if ( bias )
         this.myDrawLine( nodes.biasX, nodes.biasY, nodes.biasSubX, nodes.biasSubY );

      // dark subtraction
      if ( dark )
         this.myDrawLine( nodes.darkOptX, nodes.darkOptY, nodes.darkSubX, nodes.darkSubY );

      // flat division
      if ( flat )
         this.myDrawLine( nodes.flatDivX, nodes.flatDivY, nodes.flatX, nodes.flatY );

      // light calibration flow
      if ( light )
         this.myDrawLine( nodes.lightX, nodes.lightY, nodes.masterLightX, nodes.masterLightY );
   };

   this.drawNodes = ( nodes, bias, dark, flat, light, darkIsCalibrated, darkIsOptimized ) =>
   {
      let binningString = function( binning )
      {
         return binning ? binning + "\u00D7" + binning : "";
      };

      let exposureString = function( exposure )
      {
         return format( "%.2fs", exposure );
      };

      let filterString = function( filter )
      {
         return filter;
      };

      let typeString = function( group )
      {
         return StackEngine.imageTypeToString( group.imageType );
      };

      if ( light && light.masterFrame )
      {
         this.title( "This group already has a Master File.", this.parent.logicalPixelsToPhysical( 400 ), this.parent.logicalPixelsToPhysical( 100 ) );
         return;
      }

      // bias box
      if ( bias )
      {
         this.box( "MASTER Bias\n" + binningString( bias.binning ), nodes.biasX, nodes.biasY, 0xFF000000, 0xFFAAFFAA );
         this.operation( "\u2212", nodes.biasSubX, nodes.biasSubY, 0xFF000000, 0xFFAAFFAA );
      }

      // dark box
      if ( dark )
      {
         this.box( "MASTER Dark\n" + binningString( dark.binning ) + "\n" + exposureString( dark.exposureTime ), nodes.darkX, nodes.darkY, 0xFF000000, 0xFFAAAAAA );
         this.operation( "\u2212", nodes.darkSubX, nodes.darkSubY, 0xFF000000, 0xFFAAAAAA );
      }

      // dark calibration
      if ( bias && dark && darkIsCalibrated )
         this.operation( "\u2212", nodes.darkCalX, nodes.darkCalY, 0xFF000000, 0xFFAAFFAA );

      // dark optimization
      if ( dark && darkIsOptimized )
         this.operation( "K", nodes.darkOptX, nodes.darkOptY, 0xFF000000, 0xFFAAAAAA );

      // flat
      if ( flat )
      {
         this.box( "MASTER Flat" + "\n" + binningString( flat.binning ) + "\n" + exposureString( flat.exposureTime ) + "\n" + filterString( flat.filter ), nodes.flatX, nodes.flatY, 0xFF000000, 0xFFFFAAAA );
         this.operation( "\u00F7", nodes.flatDivX, nodes.flatDivY, 0xFF000000, 0xFFFFAAAA );
      }

      // light and master light box
      if ( light )
      {
         this.box( typeString( light ) + "\n" + binningString( light.binning ) + "\n" + exposureString( light.exposureTime ) + "\n" + filterString( light.filter ), nodes.lightX, nodes.lightY, 0xFF000000, 0xFF66CCFF );
         this.box( "CALIBRATED " + typeString( light ) + "\n" + binningString( light.binning ) + "\n" + exposureString( light.exposureTime ) + "\n" + filterString( light.filter ), nodes.masterLightX, nodes.masterLightY, 0xFF000000, 0xFF66CCFF );
      }
   };

   this.myDrawLine = ( x0, y0, x1, y1 ) =>
   {
      let p0x = this.x0 + x0;
      let p0y = this.y0 + y0;
      let p1x = this.x0 + x1;
      let p1y = this.y0 + y1;
      this.graphics.pen = new Pen( 0xFF000000, 2 );
      this.graphics.drawLine( p0x, p0y, p1x, p1y );
      this.rect.unite( p0x, p0y, p1x, p1y );
   };

   this.box = ( label, x0, y0, borderColor, backgroundColor ) =>
   {
      let sizeX = this.boxSizeX;
      let sizeY = this.boxSizeY;
      let p0x = this.x0 + x0 - sizeX / 2;
      let p0y = this.y0 + y0 - sizeY / 2;
      let p1x = this.x0 + x0 + sizeX / 2;
      let p1y = this.y0 + y0 + sizeY / 2;
      this.graphics.pen = new Pen( borderColor, this.parent.logicalPixelsToPhysical( 2 ) );
      this.graphics.brush = new Brush( backgroundColor );
      this.graphics.font = this.newFont();
      this.graphics.drawRoundedRect( p0x, p0y, p1x, p1y, this.roundRectRadius, this.roundRectRadius / sizeY * sizeX );
      this.graphics.drawTextRect( p0x, p0y, p1x, p1y, label, TextAlignment.Center | TextAlignment.VertCenter );
      this.rect.unite( p0x, p0y, p1x, p1y );
   };

   this.operation = ( label, x0, y0, borderColor, backgroundColor ) =>
   {
      let size = this.opSize;
      this.graphics.pen = new Pen( borderColor, 2 );
      this.graphics.brush = new Brush( backgroundColor );
      this.graphics.font = this.newFont( 10 );
      this.graphics.drawCircle( this.x0 + x0, this.y0 + y0, size / 2 );
      let p0x = this.x0 + x0 - size / 2;
      let p0y = this.y0 + y0 - size / 2;
      let p1x = this.x0 + x0 + size / 2;
      let p1y = this.y0 + y0 + size / 2;
      this.graphics.drawTextRect( p0x, p0y, p1x, p1y, label, TextAlignment.Center | TextAlignment.VertCenter );
      this.rect.unite( p0x, p0y, p1x, p1y );
   };

   this.title = ( label, x, y ) =>
   {
      let width = this.parent.logicalPixelsToPhysical( 800 );
      let height = this.parent.logicalPixelsToPhysical( 800 );
      let p0x = x - width / 2;
      let p0y = y - height / 2;
      let p1x = x + width / 2;
      let p1y = y + height / 2;
      this.graphics.font = this.newFont( 16 );
      this.graphics.font.bold = true;
      this.graphics.drawTextRect( p0x, p0y, p1x, p1y, label, TextAlignment.Center | TextAlignment.VertCenter );
      this.rect.unite( p0x, p0y, p1x, p1y );
   };
}

// ----------------------------------------------------------------------------
// EOF BPP-Graph.js - Released 2026-05-10T11:05:00Z
