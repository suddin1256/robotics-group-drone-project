"""Rian's V4 outline/text style without Ultralytics' default bounding-box renderer."""
import cv2
import numpy as np

WIDTH, HEIGHT = 640, 480

def draw_text(image, text, x, y, color, scale=.45):
    position = (int(x), int(y))
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale,
                (0,0,0), 4, cv2.LINE_AA)
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale,
                color, 2, cv2.LINE_AA)

def render(frame, result, names):
    """Keep the entire 4:3 image; upscale for original V4 drawing coordinates only."""
    display = cv2.resize(frame, (WIDTH,HEIGHT))
    scale_x, scale_y = WIDTH/frame.shape[1], HEIGHT/frame.shape[0]
    boxes = result.boxes
    masks = result.masks
    count = 0
    if boxes is not None and masks is not None:
        confidence = boxes.conf.detach().cpu().numpy()
        classes = boxes.cls.detach().cpu().numpy()
        rectangles = boxes.xyxy.detach().cpu().numpy()
        # Ultralytics' polygons are already mapped back to the original image;
        # raw network masks can include letterbox padding and must not be stretched.
        all_masks = masks.xy
        for score, class_id, rectangle, mask in zip(confidence,classes,rectangles,all_masks):
            if score < .25:
                continue
            if len(mask) < 3:
                continue
            polygon = np.asarray(mask,dtype=np.float32)*np.array([scale_x,scale_y])
            selected_image = np.zeros((HEIGHT,WIDTH),dtype=np.uint8)
            cv2.fillPoly(selected_image,[np.rint(polygon).astype(np.int32)],255)
            selected = selected_image > 0
            if np.count_nonzero(selected) < 100:
                continue
            class_name = names[int(class_id)]
            object_type = 'HUMAN' if class_name == 'person' else 'OBJECT'
            color = (255,200,0)
            contours,_ = cv2.findContours(selected.astype(np.uint8)*255,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            display[selected] = (.85*display[selected]+.15*np.array(color)).astype(np.uint8)
            cv2.drawContours(display,contours,-1,color,2)
            label = f'{object_type}: {class_name}'
            x = int(rectangle[0]*scale_x)
            y = max(20,int(rectangle[1]*scale_y)-8)
            text_width = cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.45,2)[0][0]
            x = max(2,min(x,WIDTH-text_width-3))
            draw_text(display,label,x,y,color)
            count += 1
    draw_text(display,f'Objects detected: {count}',10,HEIGHT-15,(255,255,255),.55)
    return display,count
