<?php

if (!defined('ABSPATH')) {
    exit;
}

add_action('after_setup_theme', function () {

    load_child_theme_textdomain(
        'mitigate-martfury-child',
        get_stylesheet_directory() . '/languages'
    );

    add_theme_support('title-tag');

    add_theme_support('post-thumbnails');

    add_theme_support('responsive-embeds');

    add_theme_support('html5', [
        'search-form',
        'gallery',
        'caption',
        'style',
        'script',
    ]);

});
