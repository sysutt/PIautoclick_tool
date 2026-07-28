// ----------------------------------------------------------------------------
// PixInsight JavaScript Runtime API - PJSR Version 2.0
// ----------------------------------------------------------------------------
// BPP-Engine.js - Released 2026-05-10T11:05:00Z
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

#include "BPP-ExecutionCache.js"
#include "BPP-ConsoleLogger.js"
#include "BPP-ProcessLogger.js"
#include "BPP-OperationQueue.js"
#include "BPP-Overscan.js"
#include "BPP-ExecutionMonitorDialog.js"
#include "BPP-BPPOperationQueue.js"
#include "BPP-PresetsDialog.js"
#include "BPP-ProcessLogDialog.js"
#include "BPP-LNReferenceSelector.js"

// Data classes
#include "BPP-Keywords.js"
#include "BPP-FileItem.js"
#include "BPP-ActiveFrame.js"
#include "BPP-FrameGroup.js"
#include "BPP-FrameGroupsManager.js"
#include "BPP-FrameSelectionParameters.js"
#include "BPP-FrameSelection.js"

// Domain classes (defined BEFORE StackEngine)
#include "BPP-SettingsManager.js"
#include "BPP-ParametersManager.js"
#include "BPP-CalibrationMatcher.js"
#include "BPP-SubframeAnalyzer.js"
#include "BPP-Processing.js"
#include "BPP-Solver.js"
#include "BPP-Pipeline.js"
#include "BPP-Diagnostic.js"

// StackEngine class
#include "BPP-StackEngine.js"

// Prototype assignments (AFTER StackEngine)
#include "BPP-Operations.js"

// ----------------------------------------------------------------------------

var engine = new StackEngine;
// default parameters
engine.parametersManager.setDefaultParameters();

// ----------------------------------------------------------------------------
// EOF BPP-Engine.js - Released 2026-05-10T11:05:00Z
