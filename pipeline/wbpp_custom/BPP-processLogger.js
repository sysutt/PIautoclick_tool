// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ProcessLogger.js - Released 2026-05-10T11:05:00Z
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

var ProcessLogger = class
{

   constructor()
   {
      this.messages = new Array;
   }

   clean()
   {
      this.messages = [];
   }

   addSuccess( title, msg )
   {
      this.messages.push(
      {
         type: 'success',
         title: title,
         msg: msg
      } );
   }

   addMessage( msg )
   {
      this.messages.push(
      {
         type: 'message',
         msg: msg
      } );
   }

   addWarning( msg )
   {
      this.messages.push(
      {
         type: 'warning',
         msg: msg
      } );
   }

   addError( msg )
   {
      this.messages.push(
      {
         type: 'error',
         msg: msg
      } );
   }

   newLine()
   {
      this.addMessage( "" );
   }

   toString()
   {
      let str = "";
      for ( let i = 0; i < this.messages.length; ++i )
      {
         let type = this.messages[ i ].type;
         let title = ( this.messages[ i ].title != undefined ) ? this.messages[ i ].title : "";
         let msg = ( this.messages[ i ].msg != undefined && this.messages[ i ].msg.length > 0 ) ? this.messages[ i ].msg : "";

         switch ( type )
         {
            case 'success':
               str += "<b>" + title + "</b>" + ( ( msg != null && !WBPPUtils.isEmptyString( msg ) ) ? ": " + msg : "" ) + "\n";
               break;
            case 'message':
               str += msg + "\n";
               break;
            case 'warning':
               str += "<b>** Warning</b>: " + this.messages[ i ].msg + "\n";
               break;
            case 'error':
               str += "<b>!!! Error: " + this.messages[ i ].msg + "</b>\n";
               break;
         }
      }
      return str;
   }

   toSanitizedString()
   {
      let string = this.toString();
      string = string.replace( /<(\/)?b>/g, "" );
      string = string.replace( /<(\/)?i>/g, "" );
      string = string.replace( /<(\/)?ul>/g, "" );
      string = string.replace( /<(\/)?li>/g, "" );
      return string;
   }

   writeToFile( fpath )
   {
      let dir = File.extractDrive( fpath ) + File.extractDirectory( fpath );
      if ( !File.directoryExists( dir ) )
         File.createDirectory( dir, true /*createIntermediateDirectories*/ );
      console.noteln( "create file: <raw>" + fpath + "</raw>" );
      let textFile = new File;
      textFile.createForWriting( fpath );
      console.noteln( "create file: <raw>" + fpath + "</raw>" );
      console.noteln( "content: ", this.toString() );
      console.noteln( "sanitized: ", this.toSanitizedString() );
      textFile.outText( this.toSanitizedString() );
      textFile.close();
   }
}

// ----------------------------------------------------------------------------
// EOF BPP-ProcessLogger.js - Released 2026-05-10T11:05:00Z
