// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// FBPP.js - Released 2026-05-10T11:05:00Z
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

#engine v8

#feature-id    FastBatchPreprocessing : Batch Processing > FastBatchPreprocessing \
                                      | Preprocessing > FastBatchPreprocessing

#feature-info  A script for fast calibration and integration of images.<br/>\
               Original script written by Kai Wiechen (c) 2012,<br/>\
               Extended and maintained by Roberto Sartori (c) 2019-2026.

#feature-icon  @script_icons_dir/FastBatchPreprocessing.svg

#include "BPP-Main.js"

CoreApplication.ensureMinimumVersion( 1, 9, 4 );

BPPmain( true /* fastMode */ ,
   BPP.Version.FBPP_ID,
   BPP.Version.FBPP_TITLE,
   BPP.Version.FBPP_SETTINGS_KEY_BASE,
   BPP.Version.FBPP_VERSION );

// ----------------------------------------------------------------------------
// EOF FBPP.js - Released 2026-05-10T11:05:00Z
