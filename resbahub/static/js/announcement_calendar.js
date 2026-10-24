
(function () {
  'use strict';

  function initAnnouncementCalendar() {
    const dateInput = document.getElementById('announcement_date');
    const weekdayDisplay = document.getElementById('selectedWeekday');
    const fullDateDisplay = document.getElementById('selectedFullDate');
    const monthYearDisplay = document.getElementById('calendarMonthYear');
    const calendarDays = document.getElementById('calendarDays');
    const previousButton = document.getElementById('previousMonth');
    const nextButton = document.getElementById('nextMonth');

    // Stop if this page does not contain the calendar.
    if (
      !dateInput ||
      !weekdayDisplay ||
      !fullDateDisplay ||
      !monthYearDisplay ||
      !calendarDays ||
      !previousButton ||
      !nextButton
    ) {
      console.error('Announcement calendar: Required HTML elements are missing.');
      return;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let displayedYear = today.getFullYear();
    let displayedMonth = today.getMonth();

    const weekdays = [
      'Sunday',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday'
    ];

    function makeDateKey(year, month, day) {
      return (
        year + '-' +
        String(month + 1).padStart(2, '0') + '-' +
        String(day).padStart(2, '0')
      );
    }

    function parseLocalDate(value) {
      if (!value) return null;

      const parts = value.split('-').map(Number);

      if (
        parts.length !== 3 ||
        parts.some(number => !Number.isInteger(number))
      ) {
        return null;
      }

      const date = new Date(parts[0], parts[1] - 1, parts[2]);

      // Reject invalid dates such as February 31.
      if (
        date.getFullYear() !== parts[0] ||
        date.getMonth() !== parts[1] - 1 ||
        date.getDate() !== parts[2]
      ) {
        return null;
      }

      return date;
    }

    function updateDatePreview() {
      const date = parseLocalDate(dateInput.value);

      if (!date) {
        weekdayDisplay.textContent = 'Choose a date';
        fullDateDisplay.textContent =
          'Your selected date will appear here.';
        renderCalendar();
        return;
      }

      weekdayDisplay.textContent = weekdays[date.getDay()];

      fullDateDisplay.textContent = date.toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric'
      });

      displayedYear = date.getFullYear();
      displayedMonth = date.getMonth();

      renderCalendar();
    }

    function renderCalendar() {
      calendarDays.replaceChildren();

      monthYearDisplay.textContent = new Date(
        displayedYear,
        displayedMonth,
        1
      ).toLocaleDateString('en-US', {
        month: 'long',
        year: 'numeric'
      });

      const firstDay = new Date(
        displayedYear,
        displayedMonth,
        1
      ).getDay();

      const daysInMonth = new Date(
        displayedYear,
        displayedMonth + 1,
        0
      ).getDate();

      // Empty spaces before the first day of the month.
      for (let i = 0; i < firstDay; i++) {
        const blank = document.createElement('span');
        blank.setAttribute('aria-hidden', 'true');
        calendarDays.appendChild(blank);
      }

      // Create the clickable dates.
      for (let day = 1; day <= daysInMonth; day++) {
        const dateButton = document.createElement('button');
        const key = makeDateKey(
          displayedYear,
          displayedMonth,
          day
        );

        const currentDate = new Date(
          displayedYear,
          displayedMonth,
          day
        );

        const todayKey = makeDateKey(
          today.getFullYear(),
          today.getMonth(),
          today.getDate()
        );

        dateButton.type = 'button';
        dateButton.className = 'calendar-day';
        dateButton.textContent = day;

        dateButton.setAttribute(
          'aria-label',
          weekdays[currentDate.getDay()] + ', ' +
          currentDate.toLocaleDateString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric'
          })
        );

        if (key === todayKey) {
          dateButton.classList.add('today');
        }

        if (key === dateInput.value) {
          dateButton.classList.add('selected');
          dateButton.setAttribute('aria-pressed', 'true');
        } else {
          dateButton.setAttribute('aria-pressed', 'false');
        }

        dateButton.addEventListener('click', function () {
          dateInput.value = key;
          updateDatePreview();
        });

        calendarDays.appendChild(dateButton);
      }
    }

    previousButton.addEventListener('click', function () {
      displayedMonth--;

      if (displayedMonth < 0) {
        displayedMonth = 11;
        displayedYear--;
      }

      renderCalendar();
    });

    nextButton.addEventListener('click', function () {
      displayedMonth++;

      if (displayedMonth > 11) {
        displayedMonth = 0;
        displayedYear++;
      }

      renderCalendar();
    });

    dateInput.addEventListener('change', updateDatePreview);

    // Show the calendar immediately instead of leaving "Loading calendar..."
    renderCalendar();
  }

  // Works whether this file loads before or after the HTML is ready.
  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      initAnnouncementCalendar
    );
  } else {
    initAnnouncementCalendar();
  }
})();
