// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-ConsoleLogger.js - Released 2026-05-10T11:05:00Z
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
 * Manages console log capture and persistence to log files on disk.
 * Wraps PixInsight's console logging API to accumulate output and
 * periodically flush it to a timestamped log file.
 */
var ConsoleLogger = class
{

   constructor()
   {
      this.logFilePath = undefined;
      this.title = "";
      this.version = "";
   }

   /**
    * Starts console log capture and writes the log file header.
    *
    * @param {String} title - The script title (e.g. "Weighted Batch Preprocessing Script")
    * @param {String} version - The script version string
    * @param {String} filePath - Absolute path to the log file
    */
   initialize( title, version, filePath )
   {
      this.logFilePath = filePath;
      this.title = title;
      this.version = version;
      console.beginLog();
      this.headerLength = console.logText().length;
      console.noteln( "<end><cbr><br>", BPP.Format.SEPARATOR );
      console.noteln( title + " " + version );
      console.noteln( BPP.Format.SEPARATOR );
   }

   /**
    * Flushes captured console output and appends it to the log file.
    */
   flush()
   {
      console.flush();
      let logData = console.endLog();
      console.beginLog();
      this._appendToFile( logData );
   }

   /**
    * Flushes remaining console output, appends it to the log file,
    * and terminates logging.
    */
   stopLogging()
   {
      console.flush();
      let logData = console.endLog();
      this._appendToFile( logData );
      this.logFilePath = undefined;
   }

   /**
    * Appends the given log data to the current log file.
    *
    * @param {ByteArray} logData - Raw console log output to append
    */
   _appendToFile( logData )
   {
      if ( this.logFilePath === undefined )
         return;

      try
      {
         let file;
         if ( File.exists( this.logFilePath ) )
         {
            file = File.openFile( this.logFilePath );
            file.seekEnd();
            // remove the main logs header to avoid the many repetitions along the logs file
            logData.remove( 0, this.headerLength );
         }
         else
            file = File.createFileForWriting( this.logFilePath );

         file.write( logData );
         file.close();
      }
      catch ( x )
      {
         if ( !engine.automationMode )
            ( new MessageBox( x.message, this.title + " " + this.version, StdIcon.Error, StdButton.Ok ) ).execute();
      }
   }

}

// ----------------------------------------------------------------------------
// EOF BPP-ConsoleLogger.js - Released 2026-05-10T11:05:00Z
