@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends.gio

import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Root-directory listing URI shape.
 *
 * The slash-juggling in [GioBackend.childUriJoinBase] is correct but
 * has zero guards — these tests pin the contract: every child of a
 * scheme root carries exactly the `scheme:///` prefix (no
 * `scheme:////`, no `//name`), and its path is absolute with no
 * empty segments.
 */
@Tag("integration")
class RootListingIntegrationTest {

    private val backend = GioBackend()

    @Test
    fun `file root children carry exactly the file triple-slash prefix`() = runTest {
        TestUtils.withGlibPump {
            val children = backend.list("file:///")
            assertFalse(children.isEmpty(), "file:/// should list top-level entries")
            for (child in children) {
                assertTrue(
                    child.uri.startsWith("file:///"),
                    "child must start with exactly file:///: ${child.uri}"
                )
                assertFalse(
                    child.uri.startsWith("file:////"),
                    "child must not carry a quadruple slash: ${child.uri}"
                )
                assertTrue(
                    child.path.startsWith("/"),
                    "path must be absolute: ${child.path}"
                )
                assertFalse(
                    child.path.contains("//"),
                    "path must not contain an empty segment: ${child.path}"
                )
                assertFalse(
                    child.name.contains("/"),
                    "root child name must be a single segment: ${child.name}"
                )
            }
        }
    }

    @Test
    fun `trash root children carry exactly the trash triple-slash prefix`() = runTest {
        TestUtils.withGlibPump {
            val children = backend.list("trash:///")
            // An empty trash is a valid listing — the shape contract
            // applies to whatever children exist.
            for (child in children) {
                assertTrue(
                    child.uri.startsWith("trash:///"),
                    "child must start with exactly trash:///: ${child.uri}"
                )
                assertFalse(
                    child.uri.startsWith("trash:////"),
                    "child must not carry a quadruple slash: ${child.uri}"
                )
                assertTrue(
                    child.path.startsWith("/"),
                    "path must be absolute: ${child.path}"
                )
                assertFalse(
                    child.path.contains("//"),
                    "path must not contain an empty segment: ${child.path}"
                )
            }
        }
    }
}
