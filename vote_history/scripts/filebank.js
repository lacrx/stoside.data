/* 
 * Fileabnk Sortable table fro style 60 (1.0)
 * by Stuart Gregg (www.civicasoft.com)
 * sgregg at civicasoft dot com
 *
 * Copyright (c) 2014 Stuart Gregg (www.civicasoft.com)
 *
 * v 1.0   - Initial release
 *
 */

// Add sortability to the type 59/60 file bank display
(function( $ ){
	$.fn.cvFilebankSortable = function( options ){

		// default settings
		var defaults = {
			fileOrder			: 'DATE'
		};
		
		// If options exist, lets merge them
		// with our default settings
		if ( options ) { 
			$.extend( defaults, options );
		}
		
		return this.each( function() {
			var self = this,
					$this = $(this),
					$name = $('th.num-alpha', $this),
					$date = $('th.date', $this);

			//$this.css({ 'background-color': 'red' });
			
			$.extend(self, {
				init: function () {
					$('th', $this).click(function () {
						var $table = $(this).parents('table').eq(0);
						$('span.sort-dir', $table).html('');
						var rows = $table.find('tr:gt(0)').toArray();

						if ($(this).hasClass('date')) {
							rows = rows.sort(self.comparerDate($(this).index()));
						}
						else if ($(this).hasClass('num-alpha')) {
							rows = rows.sort(self.comparerNumAlpha($(this).index()));
						}
						else {
							// default alpha - num sort
							rows = rows.sort(self.comparer($(this).index()));
						}

						this.asc = !this.asc;
						if (!this.asc) {
							rows = rows.reverse();
							$('span.sort-dir', $(this)).html(' -');
						}
						else {
							$('span.sort-dir', $(this)).html(' +');
						}
						for (var i = 0; i < rows.length; i++) {
							$table.append(rows[i]);
						}
					});

					if (defaults.fileOrder == 'NAME_REV') {
						// fire the first column twice
						$name.click().click();
					}
					else if (defaults.fileOrder == 'DATE') {
						// fire the date column
						$date.click();
					}
					else if (defaults.fileOrder == 'DATE_REV') {
						// fire the date column twice
						$date.click().click();
					}
					else {
						// fire the first column, for 'NAME'
						$name.click();
					}
				},
				// compare number then alpha i.e. 123 main
				comparerNumAlpha: function (index) {
					return function (a, b) {
						var valA = self.getCellValue(a, index), valB = self.getCellValue(b, index);
						var numAlphaRegExp = /(^\d+?)\s+?(.+)/;

						if (numAlphaRegExp.test(valA) && numAlphaRegExp.test(valB)) {
							var aCaptures = valA.match(numAlphaRegExp);
							var bCaptures = valB.match(numAlphaRegExp);
							if (aCaptures[1] != bCaptures[1]) {
								return aCaptures[1] - bCaptures[1];
							}
							else {
								return aCaptures[2].localeCompare(bCaptures[2]);
							}
						}
						else {
							var aNum = !isNaN(valA);
							var bNum = !isNaN(valB);
							return aNum && bNum ? valA - valB : valA.localeCompare(valB);
						}
					}
				},

				// compares date values
				comparerDate: function (index) {
					return function (a, b) {
						var valA = self.getCellValue(a, index), valB = self.getCellValue(b, index);
						var dateA = Date.parse(valA);
						var dateB = Date.parse(valB);
						var aNum = !isNaN(dateA);
						var bNum = !isNaN(dateB);
						return aNum && bNum ? dateA - dateB : valA.localeCompare(valB);
					}
				},
				// default compare
				comparer: function (index) {
					return function (a, b) {
						var valA = self.getCellValue(a, index), valB = self.getCellValue(b, index);
						var aNum = !isNaN(valA);
						var bNum = !isNaN(valB);
						return aNum && bNum ? valA - valB : valA.localeCompare(valB);
					}
				},
				// get table cell value
				getCellValue: function (row, index) {
					return $('span.compare-this', $(row).children('td').eq(index)).html();
				}
			}); // extend
			
			self.init();
			
		});
		
	}
})(jQuery);

/*
 *
 *	Set up toggling for 61/62 file bank display
 *
 */

function fbInitToggle() {
	$('a.fb-toggle').click(function (e) {
		e.preventDefault();
		var id = $(this).attr('rel');
		if (!isNaN(id)) {
			var $bucket = $('div#fbBucket' + id);
			if ($bucket.is(':visible')) {
				$bucket.hide();
				$('span', $(this)).html('+');
			}
			else {
				$bucket.show();
				$('span', $(this)).html('-');
			}
		}
	});
	$('.fbBucket').hide();
}


/*
	function initFBsortable(fileOrder) {
		jQuery('#fb-sortable-table th').click(function () {
			var $table = $(this).parents('table').eq(0);
			$('span.sort-dir', $table).html('');
			var rows = $table.find('tr:gt(0)').toArray();

			if( $(this).hasClass('date')) {
				rows = rows.sort(comparerDate($(this).index()));
			}
			else if ($(this).hasClass('num-alpha')) {
				rows = rows.sort(comparerNumAlpha($(this).index()));
			}
			else {
				// default alpha - num sort
				rows = rows.sort(comparer($(this).index()));
			}

			this.asc = !this.asc;
			if (!this.asc) {
				rows = rows.reverse();
				$('span.sort-dir', $(this)).html(' -');
			}
			else {
				$('span.sort-dir', $(this)).html(' +');
			}
			for (var i = 0; i < rows.length; i++) {
				$table.append(rows[i]);
			}
		});

		if (fileOrder == 'NAME_REV') {
			// fire the first column twice
			jQuery('#fb-sortable-table th').eq(0).click();
			jQuery('#fb-sortable-table th').eq(0).click();
		}
		else if (fileOrder == 'DATE') {
			// fire the date column
			jQuery('#fb-sortable-table th.date').click();
		}
		else if (fileOrder == 'DATE_REV') {
			// fire the date column twice
			jQuery('#fb-sortable-table th.date').click();
			jQuery('#fb-sortable-table th.date').click();
		}
		else {
			// fire the first column, for 'NAME'
			jQuery('#fb-sortable-table th').eq(0).click();
		}
	}
// compares num then alpha i.e. 1234 Main Street
function comparerNumAlpha(index) {
	return function (a, b) {
		var valA = getCellValue(a, index), valB = getCellValue(b, index);
		var numAlphaRegExp = /(^\d+?)\s+?(.+)/;

		if (numAlphaRegExp.test(valA) && numAlphaRegExp.test(valB)) {
			var aCaptures = valA.match(numAlphaRegExp);
			var bCaptures = valB.match(numAlphaRegExp);
			if (aCaptures[1] != bCaptures[1]) {
				return aCaptures[1] - bCaptures[1];
			}
			else {
				return aCaptures[2].localeCompare(bCaptures[2]);
			}
		}
		else {
			var aNum = !isNaN(valA);
			var bNum = !isNaN(valB);
			return aNum && bNum ? valA - valB : valA.localeCompare(valB);
		}

	}
}
// compares date values
function comparerDate(index) {
	return function (a, b) {
		var valA = getCellValue(a, index), valB = getCellValue(b, index);
		var dateA = Date.parse(valA);
		var dateB = Date.parse(valB);
		var aNum = !isNaN(dateA);
		var bNum = !isNaN(dateB);
		return aNum && bNum ? dateA - dateB : valA.localeCompare(valB);
	}
}
function comparer(index) {
	return function (a, b) {
		var valA = getCellValue(a, index), valB = getCellValue(b, index);
		var aNum = !isNaN(valA);
		var bNum = !isNaN(valB);
		return aNum && bNum ? valA - valB : valA.localeCompare(valB);
	}
}

function getCellValue(row, index) {
	return $('span.compare-this',$(row).children('td').eq(index)).html();
}
*/

