
var agent = typeof browser == 'undefined' ? chrome : browser;
var param = {};

for (var item of location.search.slice(1).split('&'))
{
    item = item.split('=',2);
    param[item[0]] = item[1];
}

function onContentLoad(event)
{
    msgExtInstalled.style.display = param.previous ? 'none' : '';
    msgExtUpdated.style.display   = param.previous ? '' : 'none';

    if (param.msedge)
    {
	msgBrowserName.innerText = 'Microsoft Edge';
	msgIncognitoName.innerText = 'InPrivate browsing mode';
	msgIncognitoEnable.innerText = 'Allow in InPrivate';
	linkContactSupport.href = 'http://www.internetdownloadmanager.com/support/msedge_integration.html';
    }
    else if (param.mzffox)
    {
	msgBrowserName.innerText = 'Mozilla Firefox';
	msgIncognitoName.innerText = 'Private windows';
	msgIncognitoEnable.innerText = 'Run in Private Windows';
	linkContactSupport.href = 'http://www.internetdownloadmanager.com/support/firefox_integration.html';
    }
    else if (param.opera)
    {
	msgBrowserName.innerText = 'Opera';
	msgIncognitoName.innerText = 'Private browsing mode';
	msgIncognitoEnable.innerText = 'Allow in private mode';
	linkContactSupport.href = 'http://www.internetdownloadmanager.com/support/opera_integration.html';
    }
    
    if (param.error)
    {
	msgIdmNotInstalled.hidden = false;
    }
    else if (param.consent && param.mzffox)
    {
	msgDataConsent.hidden = false;
	msgClosePage.hidden   = true;
    }
    else
    {
	msgIdmNeedsUpdate.hidden  = !param.update;
	msgIncognitoAccess.hidden = !param.incognito;
    }

    linkContactSupport.href += location.search;
    textThisYear.innerText = new Date().getFullYear();

    for (var elem of document.querySelectorAll('a[id],button[id]'))
	elem.onclick = onUserCommand;
}

function onUserCommand(event)
{
    switch (event.target.id)
    {
	case 'btnConsentAgree':
	    msgDataConsent.hidden     = true;
	    msgPolicyAccept.hidden    = false;
	    msgCloseWindow.hidden     = false;

	    msgIdmNeedsUpdate.hidden  = !param.update;
	    msgIncognitoAccess.hidden = !param.incognito;

	    agent.runtime.sendMessage([42]);
	    break;
	
	case 'btnConsentDisagree':
	    msgRefusalConfirm.hidden = !(msgDataConsent.hidden = true);
	    break;
	
	case 'btnRefusalBack':
	    msgDataConsent.hidden = !(msgRefusalConfirm.hidden = true);
	    break;

	case 'linkPolicyView':
	    msgPrivacyPolicy.hidden = !(msgDataConsent.hidden = true);
	    break;
	
	case 'btnPolicyBack':
	    msgDataConsent.hidden = !(msgPrivacyPolicy.hidden = true);
	    break;
	
	case 'btnRemoveAddon':
	    agent.runtime.sendMessage([43]);
	    break;

	case 'btnCloseWindow':
	    agent.runtime.sendMessage([38]);
	    break;

	case 'btnClosePage':
	    agent.runtime.sendMessage([38, !!param.error]);
	    break;

	default:
	    return;
    }

    event.preventDefault();
}

document.addEventListener('DOMContentLoaded', onContentLoad);
