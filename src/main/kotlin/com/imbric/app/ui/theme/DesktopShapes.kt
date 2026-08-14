package com.imbric.app.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/**
 * Desktop-grade shape tokens matching GTK 4 Adwaita design guidelines.
 * Replaces mobile Material 3 bubble radiuses (12dp-28dp) with crisp desktop curves.
 */
val DesktopShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp), // Tooltips, badges, micro chips
    small = RoundedCornerShape(6.dp),      // Buttons, breadcrumbs, sidebar items, tabs
    medium = RoundedCornerShape(8.dp),     // Address bar, menus, popovers, dropdowns
    large = RoundedCornerShape(10.dp),     // Dialogs, cards, elevated floating containers
    extraLarge = RoundedCornerShape(12.dp) // Main window root corners, large sheets
)
