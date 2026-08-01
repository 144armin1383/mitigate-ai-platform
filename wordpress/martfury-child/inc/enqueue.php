<?php

if (!defined('ABSPATH')) {
    exit;
}

add_action('wp_enqueue_scripts', function () {

    wp_enqueue_style(
        'mitigate-main',
        get_stylesheet_directory_uri() . '/assets/css/main.css',
        [],
        wp_get_theme()->get('Version')
    );

    wp_enqueue_script(
        'mitigate-main',
        get_stylesheet_directory_uri() . '/assets/js/main.js',
        [],
        wp_get_theme()->get('Version'),
        true
    );

}, 20);
