import cv2
import numpy as np
import pyautogui
import time

# Define the ROI coordinates (left, top, width, height)
roi = (750, 90, 100, 800)

# Define the reference signals
# These should be numpy arrays representing the images to track
ref_signal_long = cv2.imread('1.png')
ref_signal_short = cv2.imread('signal-short.png')

# Initialize lists to store detected signals
detected_signals_long = []
detected_signals_short = []

def is_new_signal(pt, detected_signals, distance=50):
    for signal in detected_signals:
        if np.sqrt((pt[0] - signal[0]) ** 2 + (pt[1] - signal[1]) ** 2) < distance:
            return False, len(detected_signals)
    return True, len(detected_signals)

while True:
    try:
        # Capture a screenshot within the ROI
        screenshot = pyautogui.screenshot(region=roi)
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        # Apply template Matching for long signals
        w_long, h_long = ref_signal_long.shape[0], ref_signal_long.shape[1]
        res_long = None
        for scale in np.linspace(0.2, 1.0, 20)[::-1]:
            resized_long = cv2.resize(ref_signal_long, (int(w_long * scale), int(h_long * scale)), interpolation=cv2.INTER_AREA)
            res_long = cv2.matchTemplate(screenshot, resized_long, cv2.TM_CCOEFF_NORMED)
            if np.amax(res_long) > 0.8:  # If a match is found, break the loop
                break

        threshold_long = 0.8  # set a threshold
        loc_long = np.where(res_long >= threshold_long)  # get the location of template in the screenshot

        new_signals_long = []  # Store newly detected long signals in each iteration
        pre_length_long = len(detected_signals_long)

        for pt in zip(*loc_long[::-1]):  # if the long signal is detected in screenshot
            is_new, length = is_new_signal(pt, detected_signals_long)  # check if it is a new signal
            if is_new:
                new_signals_long.append(pt)  # add the long signal to new_signals_long
                cv2.rectangle(screenshot, pt, (pt[0] + h_long, pt[1] + w_long), (0, 255, 0), 2)  # draw rectangle around the signal

        detected_signals_long.extend(new_signals_long)  # Add new long signals to the list of detected long signals

        if pre_length_long < len(detected_signals_long):
            print("Found a new long signal")

        # Apply template Matching for short signals
        w_short, h_short = ref_signal_short.shape[0], ref_signal_short.shape[1]
        res_short = None
        for scale in np.linspace(0.2, 1.0, 20)[::-1]:
            resized_short = cv2.resize(ref_signal_short, (int(w_short * scale), int(h_short * scale)), interpolation=cv2.INTER_AREA)
            res_short = cv2.matchTemplate(screenshot, resized_short, cv2.TM_CCOEFF_NORMED)
            if np.amax(res_short) > 0.8:  # If a match is found, break the loop
                break

        threshold_short = 0.8  # set a threshold
        loc_short = np.where(res_short >= threshold_short)  # get the location of template in the screenshot

        new_signals_short = []  # Store newly detected short signals in each iteration
        pre_length_short = len(detected_signals_short)

        for pt in zip(*loc_short[::-1]):  # if the short signal is detected in screenshot
            is_new, length = is_new_signal(pt, detected_signals_short)  # check if it is a new signal
            if is_new:
                new_signals_short.append(pt)  # add the short signal to new_signals_short
                cv2.rectangle(screenshot, pt, (pt[0] + h_short, pt[1] + w_short), (0, 0, 255), 2)  # draw rectangle around the signal

        detected_signals_short.extend(new_signals_short)  # Add new short signals to the list of detected short signals

        if pre_length_short < len(detected_signals_short):
            print("Found a new short signal")

        # Show the screenshot with detected signals
        cv2.imshow("Detected Signals", screenshot)
        cv2.waitKey(1)

        # Sleep for a bit before next screenshot
        time.sleep(0.5)

    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        break
