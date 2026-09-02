/*
 * TTAstroPiLot -- processing history export (standalone, one-shot; does NOT stay resident)
 * =====================================================================================
 * ASCII-ONLY ON PURPOSE: PixInsight on a Chinese-locale Windows may read a UTF-8 .js as
 * GBK and corrupt non-ASCII string literals. So this file avoids all non-ASCII; the
 * Chinese user guidance lives in the app's dialog, not here.
 *
 * WHAT IT DOES: dumps the FULL processing history (every process instance + all exact
 * parameters, via toSource()) of EVERY open image window to one text file. Dumping all
 * windows is deliberate: a real workflow often splits history across views (e.g. the
 * nebula master vs. a color/recombine copy), so we capture them all rather than guess.
 *
 * HOW TO USE (in your OWN everyday PixInsight, fully manual, no runner needed):
 *   1) Open PI, open and manually process your image (stretch / color, however you like).
 *   2) Script > Execute Script File... > pick this file > Run (F9).
 *   3) It writes to the OUT path below and prints the path in the Process Console.
 *
 * IMPORTANT: PixInsight does NOT persist processing history to disk. Process and run this
 * script in the SAME session, before closing PI -- reopening a saved image gives 0 steps.
 */

function writeOut(path, text) {
   try {
      var f = new File;
      f.createForWriting(path);
      f.outText(text);
      f.close();
      return true;
   } catch (e) {
      console.criticalln("[dump] write failed: " + e + "  (" + path + ")");
      return false;
   }
}

function histLen(w) {
   try { return w.isNull ? -1 : w.mainView.processing.length; }
   catch (e) { return -1; }
}

function typeOf(src) {
   try { var m = /new\s+([A-Za-z_]\w*)/.exec(src); return m ? m[1] : "?"; }
   catch (e) { return "?"; }
}

// Dump one view's full history into the line array L. Returns step count.
function dumpView(win, L) {
   var view = win.mainView;
   var proc = view.processing;
   var n = proc ? proc.length : 0;
   var hi = view.historyIndex;
   L.push("");
   L.push("############################################################");
   L.push("# WINDOW: " + view.id + "   (" + n + " steps, historyIndex=" + hi + ")");
   try { L.push("# file: " + (win.filePath || "(unsaved)")); } catch (e) {}
   L.push("############################################################");
   for (var j = 0; j < n; ++j) {
      var src = "";
      try { src = proc.at(j).toSource(); }
      catch (e) { src = "// (cannot serialize step " + j + ": " + e + ")"; }
      var cur = (j == hi - 1) ? " *current" : "";
      L.push("// ---------- [" + j + "] " + typeOf(src) + cur + " ----------");
      L.push(src);
      L.push("");
   }
   if (n == 0) L.push("// (no processing history on this view)");
   return n;
}

function main() {
   // Output path: baked in by the app's "export history" button; if unreplaced
   // (running straight from the repo), fall back to the system temp dir.
   var OUT = "__OUT_PATH__";
   if (OUT.indexOf("__OUT") == 0) {
      try { OUT = File.systemTempDirectory + "/tt_process_history.txt"; }
      catch (e) { OUT = "tt_process_history.txt"; }
   }

   var all = [];
   try { all = ImageWindow.windows; } catch (e) { all = []; }

   var L = [];
   L.push("# TTAstroPiLot - processing history export (all open windows)");
   try { L.push("# exported at: " + (new Date()).toISOString()); } catch (e) {}
   L.push("# open windows (id : history steps):");
   for (var i = 0; i < all.length; ++i) {
      var id = "?"; try { id = all[i].mainView.id; } catch (e) {}
      L.push("#   " + id + " : " + histLen(all[i]));
   }
   if (all.length == 0) L.push("#   (none)");
   L.push("# Each block below is a window's history; every step is that process's toSource()");
   L.push("# with ALL exact parameters. '*current' marks the current history position.");
   L.push("# NOTE: PixInsight does NOT save history to disk. A window showing 0 steps was");
   L.push("#   either a rendered view (*_annotated / preview) or an image re-opened from disk.");

   // Dump every window; count total and how many carried real history.
   var total = 0, withHist = 0;
   for (var k = 0; k < all.length; ++k) {
      var n = dumpView(all[k], L);
      total += (n > 0 ? n : 0);
      if (n > 0) ++withHist;
   }
   if (all.length == 0)
      L.push("\n// (no open image windows -- open and process your image first.)");

   if (writeOut(OUT, L.join("\n") + "\n"))
      console.noteln("[dump] " + all.length + " window(s), " + withHist +
                     " with history, " + total + " steps total -> " + OUT);
}

main();
