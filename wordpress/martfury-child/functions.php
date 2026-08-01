<?php
/**
 * MITIGATE Martfury Child Theme
 */

if (!defined('ABSPATH')) {
    exit;
}

/*
|--------------------------------------------------------------------------
| Load Theme Modules
|--------------------------------------------------------------------------
*/

$modules = [
    'setup',
    'enqueue',
    'admin',
    'api',
];

foreach ($modules as $module) {
    $file = get_stylesheet_directory() . '/inc/' . $module . '.php';

    if (file_exists($file)) {
        require_once $file;
    }
}
