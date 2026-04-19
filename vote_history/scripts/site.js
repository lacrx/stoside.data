$(function () {

    /* if is below 481px */
    if (responsive_viewport < 481) {

    }

    /* if is larger than 481px */
    if (responsive_viewport > 481) {

    }

    /* if is above or equal to 768px */
    if (responsive_viewport >= 768) {

        /* load gravatars (for Foundation) */
        $('.comment img[data-gravatar]').each(function () {
            $(this).attr('src', $(this).attr('data-gravatar'));
        });

        
        var windowHeight = $(window).height();
        //alert(windowHeight);
        $('#big-bg-image').css("display", "none");
        $('#big-bg-image').css("height", windowHeight);
        $('#big-bg-image').fadeIn( 1500 );


    }

    /* off the bat large screen actions */
    if (responsive_viewport > 1030) {

    }


    /*********************************************************************
    MAIN NAVIGATION INIT
    *********************************************************************/

    /* Toss in the 'mainNav' JSON object for the NavigationFactory
    to consume! */

    Civica_NavigationFactory.init(cvMainNav, {
        megaMenus: [{
            instanceNum: 1,
            numCols: 5,
            numSectionsPerColList: [3, 2, 1, 1, 2],
            dynamicFullWidth: true,
            extraElement: false,
            extraElementClass: 'c-1',
            showSubs: true

        },
        {
            instanceNum: 2,
            numCols: 5,
            numSectionsPerColList: [3, 2, 1, 1, 2],
            dynamicFullWidth: true,
            extraElement: false,
            extraElementClass: 'c-2',
            showSubs: true

        }]
    }).create('#dynamic-top-nav');



    /*********************************************************************
    MAIN NAVIGATION - MOUSE DETECT
    http://cherne.net/brian/resources/jquery.hoverIntent.html
    *********************************************************************/

    /* Add subtle delay when the cursor hovers over a menu and apply fade
    animations */

    /* Bind or Unbind hoverIntent based on viewport size
    - Perform this check when the page loads and upon browser resize */

    decideHoverIntent();

    $(window).resize(function () {
        decideHoverIntent();
    });


    function decideHoverIntent() {

        if (responsive_viewport < 768) {
            // Unbind hoverIntent for mobile
            unbindHoverIntent();
        } else {
            // Bind hoverIntent for desktop
            bindHoverIntent();
        }
    }


    function bindHoverIntent() {

        $('.top-bar-section .dropdown').css({
            'display': 'none',
            'visibility': 'visible'
        });

        $('.top-bar-section .has-dropdown').hoverIntent({
            over: function () {
                if (responsive_viewport >= 768) {
                    $(this).children('.dropdown').fadeIn(400);
                }
            },
            out: function () {
                if (responsive_viewport >= 768) {
                    $(this).children('.dropdown').fadeOut(300);
                }
            },
            timeout: 300
        });
    }


    function unbindHoverIntent() {

        $('.top-bar-section .has-dropdown').unbind();

        $('.top-bar-section .dropdown').css({
            'display': '',
            'visibility': ''
        });
    }




$('.streetSweep').on("click", function(e) {
    alert('This map is a general guideline for the street sweeping days on the days in the noted zones but there are exceptions. By clicking “OK” I acknowledge that I need to check the sign on the street where a vehicle is parked and abide by the sign, not this map, and cannot use this map for defense against receiving a parking citation.');
})

    //-------------------------------------------------------------------------------------------------------------------------
    //-------------------------        *LOAD ALERT         
    //-------------------------------------------------------------------------------------------------------------------------

    //Moved to the alert.asp page

        //water utilities custom code page. check if class is there, put it in the content div.
        if($(".custom-cut").length > 0) {
            $(".edtdiv").append($(".custom-cut"));
        }       
        

        $( window ).resize(function() {
            /* if is above or equal to 768px */
            if (responsive_viewport >= 768) {
                //set windowHeight variable based on the users screen height
            var windowHeight = $(window).height();
            //$('#big-bg-image').css("display", "none");
            $('#big-bg-image').css("height", windowHeight);
            //$('#big-bg-image').fadeIn( 1500 );
            }
         });


        //checks all links in edtdiv and adds external class if external
        //var exlink = new RegExp('/' + window.location.host + '/');
        //$('.edtdiv a').each(function() {
        //   if (!exlink.test(this.href)) {
               // This is an external link
        //       console.log(this.href);
        //       $(this).addClass("external")
        //  }
        //});

        /* this trims rouge spaces at the end of links in the content div. */
        setTimeout(function(){
            $('.edtdiv a').each(function(index) {
                this.href = this.href.trim();
            });
        }, 1000);
           


    //-------------------------------------------------------------------------------------------------------------------------
    //-------------------------        *Services Mega Menu         
    //-------------------------------------------------------------------------------------------------------------------------


    $(document).ready(function () {
        $('.mega-menu-1 .services').load('/custom/aja/navServices.asp');
    });

    // ------------------------------------
    // SERVICES MEGA MENU
    // ------------------------------------
    serviceTimerChecker = setTimeout(checkServiceMenuForBind, 200);
    //});

    var serviceTimer;
    function checkServiceMenuForBind() {
        if ($('#services-search-cont').length) {
            clearTimeout(serviceTimerChecker);
            // clear placeholder text when clicked
            $('input#service').bind('click', function () {
                if ($(this).val() == '' || $(this).val() == 'Search our services...') {
                    $(this).val('');
                }
            });
            addAutocomplete();
            // addFeaturedServices();
        }
        else {
            serviceTimerChecker = setTimeout(checkServiceMenuForBind, 200);
        }
    }
    var servicesID = 603;
    //var featuredServicesID = 301;
    function addAutocomplete() {
        var availableTags;
        var availableLinks;
        $.ajax({
            url: '/custom/aja/menu-ajaxsearch.asp?id=' + servicesID,
            success: function (result) {
                //console.log(result);
                $('#ajaxEvents').html(result);
                availableTags = $('#ajaxEvents input#menu-name-values').val().split(',');
                availableLinks = $('#ajaxEvents input#menu-url-values').val().split(',');
                $('input#service').autocomplete({
                    source: availableTags
                });
                // Services 'Search' button clicked...
                $('a.service-go').bind('click', function (e) {
                    e.preventDefault();
                    redirectToSearch();
                });
                // detect if enter pressed while in input field
                $('input#service').keypress(function (e) {
                    if (e.which == 13) {
                        redirectToSearch();
                    }
                });
            },
            error: function () {
                console.log('Error: Request services links');
            }
        });
    }
    function redirectToSearch() {
        //var prependQuery = 'site:' + $('input#servicesPath').val() + ' ';
        var prependQuery = '';
        window.location = '/search/default.asp?q=' + encodeURIComponent(prependQuery + $('input#service').val());
    }




    /*********************************************************************
    HOMEPAGE JS
    *********************************************************************/
if($("#homepage-flag").length > 0) {
    
  setTimeout(function () {
    //News Container scroll
     $("#news-scroll").niceScroll({cursorcolor:"#9d9d9d", cursorwidth:"10", cursorborder: "0px solid transparent", horizrailenabled:false });
     $("#news-scroll-1").niceScroll({cursorcolor:"#9d9d9d", cursorwidth:"10", cursorborder: "0px solid transparent", horizrailenabled:false });
     $("#hp-list").niceScroll({cursorcolor:"#9d9d9d", cursorwidth:"10", cursorborder: "0px solid transparent", horizrailenabled:false });
  }, 3000);

    //Homepage Top RBV Buttons
    setTimeout(function() {
            //Button 1    
            $('#hp-buttons #button-1').hover(function() {
                $('#hp-buttons #button-1 .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#hp-buttons #button-1 .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );

            //Button 2    
            $('#hp-buttons #button-2').hover(function() {
                $('#hp-buttons #button-2 .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#hp-buttons #button-2 .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );

            //Button 3    
            $('#hp-buttons #button-3').hover(function() {
                $('#hp-buttons #button-3 .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#hp-buttons #button-3 .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );

            //Additional MISC buttons, Used in special cases on FireHP and LibHP
            //Button 1    
            $('#misc-btn .fadesubtext').hover(function() {
                $('#misc-btn .fadesubtext .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#misc-btn .fadesubtext .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );

            //Button 2    
            $('#misc-btn #button-2').hover(function() {
                $('#misc-btn #button-2 .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#misc-btn #button-2 .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );

            //Button 3    
            $('#misc-btn #button-3').hover(function() {
                $('#misc-btn #button-3 .mm-button-txt-wrap span.mm-button-subtxt').fadeIn(500);
                }, function() {
                $('#misc-btn #button-3 .mm-button-txt-wrap span.mm-button-subtxt').fadeOut(250);
                }
            );


    }, 1000);

}

// Display current date via code snippet on HTML Editor pages
var currentDates = document.querySelectorAll(".edtdiv .display-current-date");
if (currentDates.length > 0) {
  var today = new Date();
  var currentdate =
    today.getMonth() + 1 + "/" + today.getDate() + "/" + today.getFullYear();
  for (var i = 0; i < currentDates.length; i++) {
    currentDates[i].innerText = "";
    currentDates[i].innerText = currentdate;
  }
}


//end of docready
});


function mm_BookMarquee(iLayoutID, sTarget, iCount, sClass, bCarousel, iSlideWidth) {
    $(sTarget).load('/custom/aja/mmBookMarquee.asp', { id: iLayoutID, cnt: iCount, cls: sClass }, function () {
        if (bCarousel == true) {
            $(sTarget + ' #carousel').bxSlider({
                minSlides: 3,
                maxSlides: 6,
                slideWidth: iSlideWidth,
                slideMargin: 10
            });
        }
    });
}


/*LIBRARY BOOK MARQUEE*/
var bMarquee = $("#books");
if (bMarquee != '' || bMarquee != undefined) {
    //alert(bMarquee);
    var marqueeID = $("#books").attr('data-source');
    mm_BookMarquee(marqueeID, '#books', '10', '', true, 150);
};





//------ Strips embedded font face / Span styles from sloppy/ depreciated markup -----------------------------------------------//
setTimeout(function() {     
     $('#page-body font').removeAttr('face');
     $('span').removeAttr('FONT-SIZE');

    //appy responsive table class to tables with more than 3 columns
    $('.edtdiv table').each(function(){ 
       //table headers are stored in a TR and often do not represent the accurate number of columns so count by the second tr           
       var totaltd = $('tbody tr:nth-child(2) td', this).length;
        //alert(totaltd);
        if (totaltd >= 3){ 
            //$(this).addClass("responsive");
        }

     });

    /* this trims rouge spaces at the end of links in the content div. */
    $('.edtdiv a').each(function(index) {
        this.href = this.href.trim();
    });


}, 500);

/*********************************************************************
Custom Slideshow Code Snippit for HTML Editor
*********************************************************************/
// Mark up required <div class="galleria" id="custom_slideshow" data-show-id="media manager id">Loading...</div>
//------------------------------------------------------------------------------------

  var iCustomSlides = $('.galleria').length;
  iCustomSlides = (iCustomSlides * 1) - 1;
  $('.galleria').each(function () {
    //alert(iCustomSlides);
    var customSlide = $('.galleria').eq(iCustomSlides);
    var customSlideID = customSlide.attr('data-show-id');

    customSlide.addClass('slide' + customSlideID);
    //alert(customSlide.attr('data-show-id'));
    if (customSlideID !== undefined) {
      Civica_Galleria.init({ mmID: customSlideID }, {  imageCrop: true }).create('.slide' + customSlideID);
    } else {
      //alert('slideId undefined');
    }
    iCustomSlides = iCustomSlides - 1;
  });


/*********************************************************************
Facebook Widget
********************************************************************
(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "//connect.facebook.net/en_US/sdk.js#xfbml=1&version=v2.0";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));
*/

/*********************************************************************
Twiiter Widget
*********************************************************************/

!function(d,s,id){var js,fjs=d.getElementsByTagName(s)[0],
p=/^http:/.test(d.location)?'http':'https';if
(!d.getElementById(id)){js=d.createElement(s);
js.id=id;js.src=p+"://platform.twitter.com/widgets.js";fjs.parentNode.insertBefore(js,fjs);}}
(document,"script","twitter-wjs" ) ;


/*********************************************************************
Instagram Widget
*********************************************************************/
function basicInstagramSlideShow(userId,clientId,domId)
{
//alert(domId);
//$(domId).css({border: solid 1px red})
$.ajax({
type: "GET",
dataType: "jsonp",
cache: false,
timeout: 10000,
url: "https://api.instagram.com/v1/users/" + userId + "/media/recent/?client_id=" + clientId,
success: function(data) {
    if( data.data ) {
        if( data.data.length > 0 ) {
            $(domId).append('<span class="img-border"></span>');
            for (var i = 0; i < data.data.length; i++) {
                            var h;
                            h = '<img src="' + data.data[i].images.thumbnail.url+ '" ></img>';
                            $(domId + ' .img-border').append(h);
            }
            $(function(){
            $(domId + ' .img-border img:gt(0)').hide();
            setInterval(function(){
                            $(domId + ' .img-border :first-child').fadeOut(800)
                            .next('img').fadeIn(800)
                            .end().appendTo(domId + ' .img-border');}, 
                            4000);
            });
        }
    }
}
})
.fail(function (e) {
        alert('Failed because of: ' + e.statusText);
        });
}

//-------------------------------------------------------------------------------------------------------------------------
//------------------------- Load the Offices Hours
//-------------------------------------------------------------------------------------------------------------------------
function displayOfficeHours() {

	$.ajax({
		url: '/custom/calendar/officesClosed.asp',
		data: 'cc=',
		success: function (cCheck) {
			$('#open-hours').html(cCheck);
		}
	});

}