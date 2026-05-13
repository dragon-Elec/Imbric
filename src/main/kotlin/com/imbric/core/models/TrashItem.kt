@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Metadata for an item in the trash bin.
 */
data class TrashItem(
    val id: Uuid = Uuid.random(),
    val name: String,
    val originalPath: String,
    val trashPath: String,
    val deletionDate: Long,
    val size: Long = 0L
)
