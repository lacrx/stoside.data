var sDefaultSearchString = 'Search the site...';

function subGrphVer(grphver) {
    document.frmGrpxVer.grpxver.value = grphver;
    document.frmGrpxVer.submit();
}


/* System Menu mouseover detect */
$('ul.system-menu').hover(function () {
    $(this).prev().addClass('hover');
},
function () {
    $(this).prev().removeClass('hover');
});


// ScrollTo Functionality
// Add the 'scrollTo' class on any element to trigger this functionality
$('a.scrollTo').click(function (e) {
    var href = $(this).attr('href');
    $.scrollTo(href, 500);
});


function frmSearchSubmit() {

    with (document.frmSearch) {

        if (q.value == '' || q.value == sDefaultSearchString) {
            alert('Please Enter a value to search');
            q.focus();
            q.value = '';
            return false;
        }

        if (CheckSearchDropdown()) {
            target = '_self';
            action = '/search/default.asp';
            return true;
        }
    }

    return false;
}


// href function for form submit 
function frmSearchGo() {

    if (frmSearchSubmit()) {
        document.frmSearch.submit();
    }
}

// clears default value from search input box
function clearSearch(el) {
    if (el.defaultValue == el.value) el.value = '';
}

function SubmitSearch() {
    document.frmSearch.submit();
}


//---------------------------------------------------------------------------------
//-- Various new window functions                                                --
//---------------------------------------------------------------------------------

var newwin;

function launchwin(winurl, winname, winfeatures) {

    newwin = window.open(winurl, winname, winfeatures);

    if (javascript_version > 1.0) {
        setTimeout('newwin.focus();', 250);
    }
}

function MM_openBrWindow(theURL, winName, features) { //v2.0
    window.open(theURL, winName, features);
}

function newwindow(theURL) {
    window.open(theURL, '', '');
}


//---------------------------------------------------------------------------------
//-- JQuery text toggle code                                                     --
//---------------------------------------------------------------------------------

function TextSizeToggle() {
    var c = Get_Cookie('fontsize');

    if (c == null) {
        //alert(c)
        c = 1;
        Set_Cookie('fontsize', c, 365, '/', '', '');
    }

    var fontElements = $('div.edtdiv, #side-nav, div.mm-buttongen-cont,  div.block-contents, p.additional-text');

    fontElements.addClass('size' + c);


    $("a#size0").click(function (event) {
        fontElements.removeClass('size1 size2').addClass('size0');
        $('a#size0').addClass('selected');
        $('a#size1').removeClass('selected');
        $('a#size2').removeClass('selected');
        Set_Cookie('fontsize', 0, 365, '/', '', '');
    });

    $("a#size1").click(function (event) {
        fontElements.removeClass('size0 size2').addClass('size1');
        $('a#size0').removeClass('selected');
        $('a#size1').addClass('selected');
        $('a#size2').removeClass('selected');
        Set_Cookie('fontsize', 1, 365, '/', '', '');
    });

    $("a#size2").click(function (event) {
        fontElements.removeClass('size0 size1').addClass('size2');
        $('a#size0').removeClass('selected');
        $('a#size1').removeClass('selected');
        $('a#size2').addClass('selected');
        Set_Cookie('fontsize', 2, 365, '/', '', '');
    });


}

//---------------------------------------------------------------------------------
//-- Cookie functions                                                            --
//---------------------------------------------------------------------------------

// this fixes an issue with the old method, ambiguous values
// with this test document.cookie.indexOf( name + "=" );
function Get_Cookie(check_name) {

    // first we'll split this cookie up into name/value pairs
    // note: document.cookie only returns name=value, not the other components
    var a_all_cookies = document.cookie.split(';');
    var a_temp_cookie = '';
    var cookie_name = '';
    var cookie_value = '';
    var b_cookie_found = false; // set boolean t/f default f

    for (i = 0; i < a_all_cookies.length; i++) {

        // now we'll split apart each name=value pair
        a_temp_cookie = a_all_cookies[i].split('=');


        // and trim left/right whitespace while we're at it
        cookie_name = a_temp_cookie[0].replace(/^\s+|\s+$/g, '');

        // if the extracted name matches passed check_name
        if (cookie_name == check_name) {

            b_cookie_found = true;
            // we need to handle case where cookie has no value but exists (no = sign, that is):
            if (a_temp_cookie.length > 1) {
                cookie_value = unescape(a_temp_cookie[1].replace(/^\s+|\s+$/g, ''));
            }
            // note that in cases where cookie is initialized but no value, null is returned
            return cookie_value;
            break;
        }

        a_temp_cookie = null;
        cookie_name = '';
    }

    if (!b_cookie_found) {
        return null;
    }
}

function Set_Cookie(name, value, expires, path, domain, secure) {

    // set time, it's in milliseconds
    var today = new Date();
    today.setTime(today.getTime());

    /*
	if the expires variable is set, make the correct
	expires time, the current script below will set
	it for x number of days, to make it for hours,
	delete * 24, for minutes, delete * 60 * 24
	*/
    if (expires) {
        expires = expires * 1000 * 60 * 60 * 24;
    }

    var expires_date = new Date(today.getTime() + (expires));

    document.cookie = name + "=" + escape(value) +
	((expires) ? ";expires=" + expires_date.toGMTString() : "") +
	((path) ? ";path=" + path : "") +
	((domain) ? ";domain=" + domain : "") +
	((secure) ? ";secure" : "");
}

function toggleSubDiv(toggle, div) {

    var myDiv = document.getElementById(div);
    var myDivToggle = document.getElementById(toggle);

    if (myDiv.style.display == 'block') {
        myDiv.style.display = 'none';
        myDivToggle.innerHTML = '<img src="/img/common/arrow_closed.png" />';
    }
    else {
        myDiv.style.display = 'block';
        myDivToggle.innerHTML = '<img src="/img/common/arrow_open.png" />';
    }
}

function StripHtml(sHtml) {

    var oldHTML = sHtml;
    var newHTML = '';
    var msg;
    var pos;
    var end;

    oldHTML = oldHTML.replace(/<\/p>/gi, '~!!BR!!~~!!BR!!~');
    oldHTML = oldHTML.replace(/<((br|ul|ol|li)[^>]*)>/gi, '~!!$1!!~');
    oldHTML = oldHTML.replace(/<\/((ul|ol|li)[^>]*)>/gi, '~!!/$1!!~');

    pos = oldHTML.search('<');
    if (pos == -1)	// no html tags found
    { newHTML = oldHTML; }

    while (pos != -1) {
        if (pos == 0) {
            end = oldHTML.search('>');
            oldHTML = oldHTML.slice(end + 1);
        }
        else {
            newHTML += oldHTML.slice(0, pos);
            end = oldHTML.search('>');
            oldHTML = oldHTML.slice(end + 1);
        }

        pos = oldHTML.search('<');
        if (pos == -1)
            newHTML += oldHTML;
    }

    newHTML = newHTML.replace(/~!!/g, '<');
    newHTML = newHTML.replace(/!!~/g, '>');
    if (newHTML.length > 0)
        while (newHTML.lastIndexOf('>') == (newHTML.length - 1)) {
            // find <
            pos = 1;
            while (newHTML.substring((newHTML.length - pos), ((newHTML.length - pos) + 1)) != '<')
                pos++;

            newHTML = newHTML.slice(0, (newHTML.length - pos));
        }

    return newHTML;
}

// Pop Up Win 
var newwin;
var civicawin;
civicawin = null;
function launchwin(winurl, winname, winfeatures) {
    newwin = window.open(winurl, winname, winfeatures);
    if (!newwin.opener) {
        newwin.opener = self
    }

    
    setTimeout('newwin.focus();', 250);
}

function civicapopupwin(winurl, winname, winfeatures) {
    civicawin = window.open(winurl, winname, winfeatures);

    if (!civicawin.opener) {
        civicawin.opener = self
    }

    setTimeout('civicawin.focus();', 250);
}


/*SEARCH FIELD AUTO COMPLETE*/


function initAzAutocomplete(id) {

  $.getJSON('/civica/azindex/aja/aja-autocomplete.asp', { 't': new Date().getTime(), 'id': id }, function (data) {

    $(".service-search #service").autocomplete({
      minLength: 2,
      source: data,
      focus: function (event, ui) {
        $("#project").val(ui.item.label);
        return false;
      },
      select: function (event, ui) {
        $(".service-search #service").val(ui.item.label);
        $(".service-search #safety").val(ui.item.label);
        $(".frmService").attr("action", ui.item.url);
        $(".frmService").attr("target", ui.item.target);
        //alert('hello');
        return false;
      }
    })
			.data("autocomplete")._renderItem = function (ul, item) {
			  return $("<li></li>")
					.data("item.autocomplete", item)
					.append("<a><strong>" + item.label + "</strong><br>" + item.desc + "</a>")
					.appendTo(ul);
			};

    // check the text box is good to go
    $("#frmService").submit(function () {
      //if ($(".frmService").attr("action") != '') {

      $(".frmService").attr("action") = $(".service-search #service").val('');

      if ($(".service-search #service").val() == $(".service-search #safety").val()) {
        $(".service-search #service").val('');
        return true;
      }
      //}
      return false;
    });

    $('#service-search .service-go').click(function (e) {
      e.preventDefault();
      $('#frmService').submit();
    });

  });
}

//display city open Friday or not text
function displayCityFirdayText() {
  $.ajax({
    url: '/custom/hompageHolidaycheck.asp',
    data: 'cc=',
    success: function (cCheck) {
      $('#header-notify-txt').html(cCheck);
    }
  });  
}

function submitStatusForm() {

    var formAction = $('#frmStatus').attr('action');
    var formData = $('#frmStatus').serializeArray();

    $('.form-container').load(formAction, formData, function () {
        //$(this).append('<hr /><a id="modal-cancel" class="button secondary cancel" style="margin-left: 0;" href="javascript:Civica_Modal.hideOverlay();">Close</a>');
        Civica_Modal.hideOverlay();
    });
}

function submitServicesForm() {

    var formAction = $('#frmServices').attr('action');
    var formData = $('#frmServices').serialize();

    //var pID = $('input[name="PageID"]').val();

    $('.form-container').load(formAction, formData, function () {
        //$(this).append('<hr /><a id="modal-cancel" class="button secondary cancel" style="margin-left: 0;" href="javascript:Civica_Modal.hideOverlay();">Close</a>');
        Civica_Modal.hideOverlay();
    });
}

function submitNotesForm() {

    var formAction = $('#frmNotes').attr('action');
    var formData = $('#frmNotes').serialize();

    if ($('textarea[name="notes"]').val() != '') {

        $('.form-container').load(formAction, formData, function () {
            //$(this).append('<hr /><a id="modal-cancel" class="button secondary cancel" style="margin-left: 0;" href="javascript:Civica_Modal.hideOverlay();">Close</a>');
            Civica_Modal.hideOverlay();
        });
    } else {
        alert('You cannot submit a blank note.');
    }
}

function submitIssueForm() {

    if ($('textarea[name="Problem"]').val() != '') {

        var formAction = $('#frmIssue').attr('action');
        var formData = $('#frmIssue').serialize();

        $('.form-container').load(formAction, formData);

    } else {
        alert('You cannot submit a blank description.');
    }
}
