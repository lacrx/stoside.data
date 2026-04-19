// JScript File

var dbgDiv = null;

//---------------------------------------------------------------------------
//  Debug div...
//---------------------------------------------------------------------------
function CreateDbg()
{
	dbgDiv = document.createElement("DIV");
	with(dbgDiv){
		id = 'dbgDiv';
		with(style) {
			position = "absolute";
			display= "block";
			left = "000px";
			top = "400px";
			width = '200px';
			height = '400px';
			border = 'solid 1px black';
			background = '#ffffff';
			fontSize = '9px';
			overflowY = 'auto';
		}
	}
	document.body.appendChild(dbgDiv);
}

function DbgWriteLine( sIn )
{
	if( dbgDiv )
	{
		dbgDiv.innerHTML += sIn + '<br/>';
		dbgDiv.scrollTop = dbgDiv.scrollHeight;
	}
}


//---------------------------------------------------------------------------
//  Get reference to an object
//---------------------------------------------------------------------------
function cm_f_getRefToDiv(divID,oDoc)
{
	if( !oDoc )
	{ 
		oDoc = document;
	}
	if( document.layers ) 
	{
		if( oDoc.layers[divID] ) 
		{ 
			return oDoc.layers[divID]; 
		} 
		else
		{
			//repeatedly run through all child layers
			for( var x = 0, y; !y && x < oDoc.layers.length; x++ )
			{
				 //on success, return that layer, else return nothing
				 y = getRefToDiv(divID,oDoc.layers[x].document); 
			}
		return y; 
		} 
	}
	if( document.getElementById ) 
	{
		return document.getElementById(divID); 
	}
	if( document.all ) 
	{
		return document.all[divID]; 
	}
	return false;
}

//---------------------------------------------------------------------------
//  Position a div
//---------------------------------------------------------------------------
function cm_f_moveDivTo(x,y,oThis)
{
	var myReference;
	if( oThis.style )
	{ 
		myReference = oThis.style;
	}
	var noPx = document.childNodes ? 'px' : 0;
	myReference.left = x + noPx;
	myReference.top = y + noPx;
}

//---------------------------------------------------------------------------
// load xml document
//---------------------------------------------------------------------------

function loadXMLDoc(fname)
{
	if( grpxver == 'mob' )
	{
		return null;
	}
	
	var Doc;
	
	//if (document.all)
	if (cm_f_IsIE())
	{
		var progIDs = [ 'Msxml2.DOMDocument.6.0', 'Msxml2.DOMDocument.3.0'];
	 
		for (var i = 0; i < progIDs.length; i++) 
		{
			try 
			{
				Doc = new ActiveXObject(progIDs[i]);
				Doc.async=false;
				Doc.load(fname);
				return(Doc);
			}
			catch (ex) {
			}
		}
	 
		return null;
	}
	else
	{
		try //Firefox, Mozilla, Opera, etc.
		{
			var xmlhttp = new window.XMLHttpRequest();
			xmlhttp.open("GET",fname,false);
			xmlhttp.send(null);
			Doc = xmlhttp.responseXML.documentElement;
			return(Doc);
			
		}
		catch(e) 
		{
			alert(e.message)
		}
		try
		{
			Doc.async=false;
			Doc.load(fname);
			return(Doc);
		}
		catch(e) 
		{
			alert(e.message)
		}
	}
	return(null);
} 

//---------------------------------------------------------------------------
// convert string into xml document
//---------------------------------------------------------------------------
function cm_f_XmlParseString(txt)
{
	var Doc = null;

	//if (document.all) 
	if (cm_f_IsIE())
	{
		var progIDs = [ 'Msxml2.DOMDocument.6.0', 'Msxml2.DOMDocument.3.0'];
	 
		for (var i = 0; i < progIDs.length; i++) 
		{
			try 
			{
				Doc = new ActiveXObject(progIDs[i]);
				Doc.async="false";
				Doc.loadXML(txt);
				return Doc; 
			}
			catch (ex) {
			}
		}
	 
		return null;
	}
	else
  {
		parser=new DOMParser();
		Doc=parser.parseFromString(txt,"text/xml");
		return Doc;
  }
}
//---------------------------------------------------------------------------
// Checck document.all and the user agent for i.e. 10 +
//---------------------------------------------------------------------------
function cm_f_IsIE() {
	var isAtLeastIE11 = !!(navigator.userAgent.match(/Trident/) && !navigator.userAgent.match(/MSIE/));
	return isAtLeastIE11 || document.all;
}

//---------------------------------------------------------------------------
// Add an on load event
//---------------------------------------------------------------------------
function cvAddLoadEvent(func) 
{   
	var oldonload = window.onload;   
	if (typeof window.onload != 'function')
	{   
		window.onload = func;   
	} 
	else 
	{   
		window.onload = function() {   
		if (oldonload)
		{   
			oldonload();   
		}   
		func();   
		}   
	}   
}   

//---------------------------------------------------------------------------
// Add an on resize event
//---------------------------------------------------------------------------
function cvAddResizeEvent(func) 
{   
	var oldonresize = window.onresize;   
	if (typeof window.onresize != 'function')
	{   
		window.onresize = func;   
	} 
	else 
	{   
		window.onresize = function() {   
		if (oldonresize)
		{   
			oldonresize();   
		}   
		func();   
		}   
	}   
}

//---------------------------------------------------------------------------
// Add an on resize event
//---------------------------------------------------------------------------
function GetXmlHttpObject()
{
	if (window.XMLHttpRequest)
  {
		// code for IE7+, Firefox, Chrome, Opera, Safari
		return new XMLHttpRequest();
  }
	if (window.ActiveXObject)
  {
		// code for IE6, IE5
		return new ActiveXObject("Microsoft.XMLHTTP");
  }
	return null;
}

