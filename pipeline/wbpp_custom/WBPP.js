// ----------------------------------------------------------------------------
// WBPP.js — TTAstroPiLot custom automation copy (filter-tag stacking).
// 基于系统 WeightedBatchPreprocessing 3.0.1 复制;仅改动:
//   - parseFileParameters 支持 "dir=<路径>|<滤镜>" + 只加 .fit/.xisf(见 BPP-Automation.js)
//   - ImageSolver include 换成空壳 stub(platesolve=false 不解析,见 BPP-Solver.js)
//   - 去掉 #feature-* 指令(-r= 自动化不需要 GUI 菜单注册;避免与系统已注册的同名 feature 无谓交互)
// ----------------------------------------------------------------------------

#engine v8

#include "BPP-Main.js"

CoreApplication.ensureMinimumVersion( 1, 9, 4 );

BPPmain( false /* fastMode */ ,
   BPP.Version.WBPP_ID,
   BPP.Version.WBPP_TITLE,
   BPP.Version.WBPP_SETTINGS_KEY_BASE,
   BPP.Version.WBPP_VERSION );
