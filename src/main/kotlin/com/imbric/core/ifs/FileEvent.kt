package com.imbric.core.ifs

sealed class FileEvent {
    data class Created(val uri: String) : FileEvent()
    data class Deleted(val uri: String) : FileEvent()
    data class Modified(val uri: String) : FileEvent()
    data class Renamed(val from: String, val to: String) : FileEvent()
}
