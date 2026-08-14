import unittest
from .compressor import (
    clean_path,
    compress_warnings,
    compress_errors,
    compress_stacktrace,
    compress_glib_warnings,
    format_pipeline_timer
)
from .daemon import PROJECT_ROOT

class TestCompressor(unittest.TestCase):
    def test_clean_path(self):
        root = str(PROJECT_ROOT)
        self.assertEqual(clean_path(f"file://{root}/src/App.kt"), "src/App.kt")
        self.assertEqual(clean_path(f"{root}/src/App.kt"), "src/App.kt")
        self.assertEqual(clean_path("src/App.kt"), "src/App.kt")
        self.assertEqual(clean_path(""), "")

    def test_compress_warnings_collapses_duplicates(self):
        root = str(PROJECT_ROOT)
        lines = [
            f"w: file://{root}/src/MainWindow.kt:103:59 Unnecessary non-null assertion (!!)",
            f"w: file://{root}/src/MainWindow.kt:117:56 Unnecessary non-null assertion (!!)",
            f"w: file://{root}/src/MainWindow.kt:167:59 Unnecessary non-null assertion (!!)",
            f"w: file://{root}/src/MainWindow.kt:137:116 'val Icons.Filled.ViewList' is deprecated",
            f"w: file://{root}/src/ListingDirectory.kt:144:61 No cast needed.",
            f"w: file://{root}/src/ListingDirectory.kt:145:57 No cast needed.",
        ]
        result = compress_warnings(lines)
        self.assertIn("📁 src/MainWindow.kt", result)
        self.assertIn("L103, L117, L167 (3x): Unnecessary non-null assertion (!!)", result)
        self.assertIn("L137: 'val Icons.Filled.ViewList' is deprecated", result)
        self.assertIn("📁 src/ListingDirectory.kt", result)
        self.assertIn("L144, L145 (2x): No cast needed.", result)

    def test_compress_errors_and_unparsed_safety(self):
        root = str(PROJECT_ROOT)
        lines = [
            f"e: file://{root}/src/App.kt:42:10 Unresolved reference 'foo'",
            f"e: file://{root}/src/App.kt:45:15 Type mismatch: expected Int, found String",
            "Custom unknown compiler plugin error: XYZ failed",
        ]
        result = compress_errors(lines)
        self.assertIn("❌ src/App.kt", result)
        self.assertIn("L42:10: Unresolved reference 'foo'", result)
        self.assertIn("L45:15: Type mismatch: expected Int, found String", result)
        # Verify unknown/unparsed error is NOT dropped
        self.assertIn("Custom unknown compiler plugin error: XYZ failed", result)

    def test_compress_stacktrace(self):
        lines = [
            "java.lang.NullPointerException: state was null",
            "    at com.imbric.core.ifs.directories.DirState.refresh(DirState.kt:120)",
            "    at org.gradle.internal.dispatch.ReflectionDispatch.dispatch(ReflectionDispatch.java:36)",
            "    at org.gradle.internal.dispatch.ReflectionDispatch.dispatch(ReflectionDispatch.java:24)",
            "    at jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:104)",
            "    at java.lang.reflect.Method.invoke(Method.java:565)",
            "    at com.imbric.app.viewmodel.FileBrowserViewModel.navigateTo(FileBrowserViewModel.kt:45)",
            "    at org.gradle.process.internal.worker.child.ActionExecutionWorker.execute(ActionExecutionWorker.java:56)",
        ]
        result = compress_stacktrace(lines)
        self.assertIn("com.imbric.core.ifs.directories.DirState.refresh", result)
        self.assertIn("com.imbric.app.viewmodel.FileBrowserViewModel.navigateTo", result)
        self.assertIn("[... 4 internal framework frames skipped ...]", result)
        self.assertIn("[... 1 internal framework frames skipped ...]", result)

    def test_compress_glib_warnings(self):
        lines = [
            "(com.imbric:12345): GLib-GIO-CRITICAL **: g_file_info_get_attribute_byte_string: assertion 'G_IS_FILE_INFO (info)' failed",
            "(com.imbric:12345): GLib-GIO-CRITICAL **: g_file_info_get_attribute_byte_string: assertion 'G_IS_FILE_INFO (info)' failed",
            "(com.imbric:12345): GLib-GIO-CRITICAL **: g_file_info_get_attribute_byte_string: assertion 'G_IS_FILE_INFO (info)' failed",
            "GLib-WARNING **: g_set_error: custom error",
            "Random native C error output",
        ]
        result = compress_glib_warnings(lines)
        self.assertIn("⚠️ [GLib-GIO-CRITICAL] (3x) g_file_info_get_attribute_byte_string: assertion 'G_IS_FILE_INFO (info)' failed", result)
        self.assertIn("⚠️ [GLib-WARNING] g_set_error: custom error", result)
        # Unparsed lines passed through
        self.assertIn("⚠️ Random native C error output", result)

    def test_format_pipeline_timer(self):
        line = "[PIPELINE] 135ms (ui_click=+0ms (file:///data) → gio_list_done=+134ms [990] → ui_rendered=+245ms [990])"
        result = format_pipeline_timer(line)
        self.assertIn("⏱️  [PIPELINE TIMELINE] Total: 135ms", result)
        self.assertIn("1. ui_click=+0ms (file:///data)", result)
        self.assertIn("2. gio_list_done=+134ms [990]", result)
        self.assertIn("3. ui_rendered=+245ms [990]", result)

    def test_empty_inputs(self):
        self.assertEqual(compress_warnings([]), "")
        self.assertEqual(compress_errors([]), "")
        self.assertEqual(compress_stacktrace([]), "")
        self.assertEqual(compress_glib_warnings([]), "")
        self.assertEqual(format_pipeline_timer(""), "")

if __name__ == "__main__":
    unittest.main()
