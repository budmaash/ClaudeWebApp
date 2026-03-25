from copy import deepcopy


SHELL_CONFIG = {
    "site_title": "Hasan Tutoring Static Shell",
    "description": "Reusable Flask shell for the Hasan Tutoring header and footer.",
    "favicon": "https://images.squarespace-cdn.com/content/v1/6719d488c1d7644f3ed87605/f9b991be-6150-45fb-9276-f2464992f9d7/favicon.ico?format=100w",
    "body_id": "collection-698e6a52b79d7e742279daa8",
    "body_class": "tweak-blog-alternating-side-by-side-width-full tweak-blog-alternating-side-by-side-image-aspect-ratio-11-square tweak-blog-alternating-side-by-side-text-alignment-left tweak-blog-alternating-side-by-side-read-more-style-show tweak-blog-alternating-side-by-side-image-text-alignment-middle tweak-blog-alternating-side-by-side-delimiter-bullet tweak-blog-alternating-side-by-side-meta-position-top tweak-blog-alternating-side-by-side-primary-meta-categories tweak-blog-alternating-side-by-side-secondary-meta-date tweak-blog-alternating-side-by-side-excerpt-show form-field-style-solid form-field-shape-square form-field-border-all form-field-checkbox-type-icon form-field-checkbox-fill-solid form-field-checkbox-color-inverted form-field-checkbox-shape-square form-field-checkbox-layout-stack form-field-radio-type-icon form-field-radio-fill-solid form-field-radio-color-normal form-field-radio-shape-pill form-field-radio-layout-stack form-field-survey-fill-solid form-field-survey-color-normal form-field-survey-shape-pill form-field-hover-focus-outline form-submit-button-style-label tweak-global-animations-complexity-level-detailed tweak-global-animations-animation-style-fade tweak-global-animations-animation-type-none tweak-global-animations-animation-curve-ease tweak-blog-masonry-width-full tweak-blog-masonry-text-alignment-left tweak-blog-masonry-primary-meta-categories tweak-blog-masonry-secondary-meta-date tweak-blog-masonry-meta-position-top tweak-blog-masonry-read-more-style-show tweak-blog-masonry-delimiter-space tweak-blog-masonry-image-placement-above tweak-blog-masonry-excerpt-show tweak-portfolio-grid-overlay-width-full tweak-portfolio-grid-overlay-height-large tweak-portfolio-grid-overlay-image-aspect-ratio-11-square tweak-portfolio-grid-overlay-text-placement-center tweak-portfolio-grid-overlay-show-text-after-hover image-block-poster-text-alignment-center image-block-card-content-position-center image-block-card-text-alignment-center image-block-overlap-content-position-center image-block-overlap-text-alignment-left image-block-collage-content-position-top image-block-collage-text-alignment-left image-block-stack-text-alignment-left tweak-blog-single-column-width-full tweak-blog-single-column-text-alignment-left tweak-blog-single-column-image-placement-above tweak-blog-single-column-delimiter-bullet tweak-blog-single-column-read-more-style-hide tweak-blog-single-column-primary-meta-date tweak-blog-single-column-secondary-meta-none tweak-blog-single-column-meta-position-above-title tweak-blog-single-column-content-full-post header-width-full tweak-transparent-header tweak-fixed-header-style-basic tweak-blog-item-width-medium tweak-blog-item-text-alignment-center tweak-blog-item-meta-position-above-title tweak-blog-item-show-date tweak-blog-item-delimiter-bullet tweak-blog-side-by-side-width-full tweak-blog-side-by-side-image-placement-left tweak-blog-side-by-side-image-aspect-ratio-11-square tweak-blog-side-by-side-primary-meta-categories tweak-blog-side-by-side-secondary-meta-date tweak-blog-side-by-side-meta-position-top tweak-blog-side-by-side-text-alignment-left tweak-blog-side-by-side-image-text-alignment-middle tweak-blog-side-by-side-read-more-style-show tweak-blog-side-by-side-delimiter-bullet tweak-blog-side-by-side-excerpt-show primary-button-style-solid primary-button-shape-pill secondary-button-style-solid secondary-button-shape-square tertiary-button-style-solid tertiary-button-shape-square tweak-events-stacked-width-full tweak-events-stacked-height-large tweak-events-stacked-show-past-events tweak-events-stacked-show-thumbnails tweak-events-stacked-thumbnail-size-32-standard tweak-events-stacked-date-style-side-tag tweak-events-stacked-show-time tweak-events-stacked-show-location tweak-events-stacked-show-excerpt tweak-blog-basic-grid-width-inset tweak-blog-basic-grid-image-aspect-ratio-32-standard tweak-blog-basic-grid-text-alignment-center tweak-blog-basic-grid-delimiter-bullet tweak-blog-basic-grid-image-placement-above tweak-blog-basic-grid-read-more-style-show tweak-blog-basic-grid-primary-meta-categories tweak-blog-basic-grid-secondary-meta-date tweak-blog-basic-grid-excerpt-show tweak-portfolio-grid-basic-width-full tweak-portfolio-grid-basic-height-large tweak-portfolio-grid-basic-image-aspect-ratio-11-square tweak-portfolio-grid-basic-text-alignment-left tweak-portfolio-grid-basic-hover-effect-fade header-overlay-alignment-center tweak-portfolio-index-background-link-format-stacked tweak-portfolio-index-background-width-full tweak-portfolio-index-background-height-large tweak-portfolio-index-background-vertical-alignment-middle tweak-portfolio-index-background-horizontal-alignment-center tweak-portfolio-index-background-delimiter-none tweak-portfolio-index-background-animation-type-fade tweak-portfolio-index-background-animation-duration-medium tweak-portfolio-hover-follow-layout-inline tweak-portfolio-hover-follow-delimiter-bullet tweak-portfolio-hover-follow-animation-type-fade tweak-portfolio-hover-follow-animation-duration-fast tweak-portfolio-hover-static-layout-inline tweak-portfolio-hover-static-front tweak-portfolio-hover-static-delimiter-hyphen tweak-portfolio-hover-static-animation-type-fade tweak-portfolio-hover-static-animation-duration-fast hide-opentable-icons opentable-style-dark tweak-product-quick-view-button-style-floating tweak-product-quick-view-button-position-bottom tweak-product-quick-view-lightbox-excerpt-display-truncate tweak-product-quick-view-lightbox-show-arrows tweak-product-quick-view-lightbox-show-close-button tweak-product-quick-view-lightbox-controls-weight-light native-currency-code-usd collection-type-page collection-698e6a52b79d7e742279daa8 collection-layout-full-width mobile-style-available sqs-seven-one seven-one-global-animations",
    "home_url": "https://www.hasantutoring.com/",
    "skip_to_content_url": "https://www.hasantutoring.com/start-here-w/-banner#page",
    "login_url": "https://www.hasantutoring.com/start-here-w/-banner#",
    "cta": {
        "href": "https://www.hasantutoring.com/member-home",
        "text": "Member Home",
    },
    "navigation": [
        {"href": "https://www.hasantutoring.com/", "label": "Start Here", "home": True},
        {"href": "https://www.hasantutoring.com/tests-1", "label": "Test Info"},
        {"href": "https://www.hasantutoring.com/act-vs-sat", "label": "ACT vs. SAT"},
        {"href": "https://www.hasantutoring.com/test-prep-options", "label": "Why Tutoring?"},
        {"href": "https://www.hasantutoring.com/about-me", "label": "About Me"},
        {"href": "https://www.hasantutoring.com/faqs", "label": "FAQs"},
        {"href": "https://www.hasantutoring.com/blog", "label": "Blog"},
    ],
    "footer": {
        "columns": [
            {
                "heading": "Helpful Links",
                "html": [
                    '<p><a data-preserve-html-node="true" href="http://www.actstudent.org/regist/dates.html" target="_blank">ACT Testing Dates</a></p>',
                    '<p><a data-preserve-html-node="true" href="https://services.actstudent.org/OA_HTML/actibeCAcdLogin.jsp" target="_blank">Sign Up for the ACT</a></p>',
                    '<p><a data-preserve-html-node="true" href="http://sat.collegeboard.org/register/sat-us-dates" target="_blank">SAT Testing Dates</a></p>',
                    '<p><a data-preserve-html-node="true" href="http://sat.collegeboard.org/login?applicationId=115&amp;destinationpage=https://nsat.collegeboard.org/satweb/login.jsp&amp;view=NSAT" target="_blank">Sign Up for the SAT</a></p>',
                    '<p><a data-preserve-html-node="true" href="https://majid-hasan.squarespace.com/test-prep-options#Pricing" target="_blank">How Much for Tutoring?</a></p>',
                ],
            },
            {
                "heading": "Contact Me",
                "html": [
                    '<p><a href="mailto:majid@hasantutoring.com">Majid@HasanTutoring.com</a><br>913.210.0611<br><a href="https://www.hasantutoring.com/contact-pages">Or Send Me a Message</a></p>'
                ],
            },
            {
                "heading": "My Philosophy",
                "html": [
                    "<p><strong>Recogize these are exams are extremely repetitive and therefore LEARNABLE.</strong> There are only so many different types of questions, and I teach students to learn to recognize them and the simple steps to answer each one. I meet one-on-one with each student, track their progress, and focus on their needs at their pace.</p>"
                ],
            },
        ]
    },
}


def create_shell_config(overrides=None):
    config = deepcopy(SHELL_CONFIG)
    if not overrides:
        return config

    for key, value in overrides.items():
        if key == "cta" and isinstance(value, dict):
            config["cta"].update(value)
        elif key == "footer" and isinstance(value, dict):
            config["footer"].update(value)
        else:
            config[key] = value
    return config
