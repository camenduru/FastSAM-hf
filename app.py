from ultralytics import YOLO
import numpy as np
import matplotlib.pyplot as plt
import gradio as gr
import cv2
import torch
from PIL import Image

model = YOLO('checkpoints/FastSAM.pt')  # load a custom model


def fast_process(annotations, image, high_quality, device):
    if isinstance(annotations[0],dict):
        annotations = [annotation['segmentation'] for annotation in annotations]

    original_h = image.height
    original_w = image.width
    fig = plt.figure(figsize=(10, 10))
    plt.imshow(image)
    if high_quality == True:
        if isinstance(annotations[0],torch.Tensor):
            annotations = np.array(annotations.cpu())
        for i, mask in enumerate(annotations):
            mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            annotations[i] = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((8, 8), np.uint8))
    if device == 'cpu':
        annotations = np.array(annotations)
        fast_show_mask(annotations,
                       plt.gca(),
                       bbox=None,
                       points=None,
                       pointlabel=None,
                       retinamask=True,
                       target_height=original_h,
                       target_width=original_w)
    else:
        if isinstance(annotations[0],np.ndarray):
            annotations = torch.from_numpy(annotations)
        fast_show_mask_gpu(annotations,
                           plt.gca(),
                           bbox=None,
                           points=None,
                           pointlabel=None)
    if isinstance(annotations, torch.Tensor):
        annotations = annotations.cpu().numpy()
    if high_quality == True:
        contour_all = []
        temp = np.zeros((original_h, original_w,1))
        for i, mask in enumerate(annotations):
            if type(mask) == dict:
                mask = mask['segmentation']
            annotation = mask.astype(np.uint8)
            contours, _ = cv2.findContours(annotation, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                contour_all.append(contour)
        cv2.drawContours(temp, contour_all, -1, (255, 255, 255), 2)
        color = np.array([0 / 255, 0 / 255, 255 / 255, 0.8])
        contour_mask = temp / 225 * color.reshape(1, 1, -1)
        plt.imshow(contour_mask)

    plt.axis('off')
    plt.tight_layout()
    return fig


#   CPU post process
def fast_show_mask(annotation, ax, bbox=None, 
                   points=None, pointlabel=None,
                   retinamask=True, target_height=960,
                   target_width=960):
    msak_sum = annotation.shape[0]
    height = annotation.shape[1]
    weight = annotation.shape[2]
    # 将annotation 按照面积 排序
    areas = np.sum(annotation, axis=(1, 2))
    sorted_indices = np.argsort(areas)[::1]
    annotation = annotation[sorted_indices]

    index = (annotation != 0).argmax(axis=0)
    color = np.random.random((msak_sum,1,1,3))
    transparency = np.ones((msak_sum,1,1,1)) * 0.6
    visual = np.concatenate([color,transparency],axis=-1)
    mask_image = np.expand_dims(annotation,-1) * visual

    show = np.zeros((height,weight,4))

    h_indices, w_indices = np.meshgrid(np.arange(height), np.arange(weight), indexing='ij')
    indices = (index[h_indices, w_indices], h_indices, w_indices, slice(None))
    # 使用向量化索引更新show的值
    show[h_indices, w_indices, :] = mask_image[indices]
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, edgecolor='b', linewidth=1))
    # draw point
    if points is not None:
        plt.scatter([point[0] for i, point in enumerate(points) if pointlabel[i]==1], [point[1] for i, point in enumerate(points) if pointlabel[i]==1], s=20, c='y')
        plt.scatter([point[0] for i, point in enumerate(points) if pointlabel[i]==0], [point[1] for i, point in enumerate(points) if pointlabel[i]==0], s=20, c='m')
    
    if retinamask==False:
        show = cv2.resize(show,(target_width,target_height),interpolation=cv2.INTER_NEAREST)
    ax.imshow(show)


def fast_show_mask_gpu(annotation, ax,
                       bbox=None, points=None, 
                       pointlabel=None):
    msak_sum = annotation.shape[0]
    height = annotation.shape[1]
    weight = annotation.shape[2]
    areas = torch.sum(annotation, dim=(1, 2))
    sorted_indices = torch.argsort(areas, descending=False)
    annotation = annotation[sorted_indices]
    # 找每个位置第一个非零值下标
    index = (annotation != 0).to(torch.long).argmax(dim=0)
    color = torch.rand((msak_sum,1,1,3)).to(annotation.device)
    transparency = torch.ones((msak_sum,1,1,1)).to(annotation.device) * 0.6
    visual = torch.cat([color,transparency],dim=-1)
    mask_image = torch.unsqueeze(annotation,-1) * visual
    # 按index取数，index指每个位置选哪个batch的数，把mask_image转成一个batch的形式
    show = torch.zeros((height,weight,4)).to(annotation.device)
    h_indices, w_indices = torch.meshgrid(torch.arange(height), torch.arange(weight))
    indices = (index[h_indices, w_indices], h_indices, w_indices, slice(None))
    # 使用向量化索引更新show的值
    show[h_indices, w_indices, :] = mask_image[indices]
    show_cpu = show.cpu().numpy()
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, edgecolor='b', linewidth=1))
    # draw point
    if points is not None:
        plt.scatter([point[0] for i, point in enumerate(points) if pointlabel[i]==1], [point[1] for i, point in enumerate(points) if pointlabel[i]==1], s=20, c='y')
        plt.scatter([point[0] for i, point in enumerate(points) if pointlabel[i]==0], [point[1] for i, point in enumerate(points) if pointlabel[i]==0], s=20, c='m')
    ax.imshow(show_cpu)

# post_process(results[0].masks, Image.open("../data/cake.png"))

def predict(input, input_size=512, high_visual_quality=True):
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    input_size = int(input_size)  # 确保 imgsz 是整数
    results = model(input, device=device, retina_masks=True, iou=0.7, conf=0.25, imgsz=input_size)
    pil_image = fast_process(annotations=results[0].masks.data,
                             image=input, high_quality=high_visual_quality, device=device)
    return pil_image

# input_size=1024
# high_quality_visual=True
# inp = 'assets/sa_192.jpg'
# input = Image.open(inp)
# device = 'cuda' if torch.cuda.is_available() else 'cpu'
# input_size = int(input_size)  # 确保 imgsz 是整数
# results = model(input, device=device, retina_masks=True, iou=0.7, conf=0.25, imgsz=input_size)
# pil_image = fast_process(annotations=results[0].masks.data,
#                             image=input, high_quality=high_quality_visual, device=device)
demo = gr.Interface(fn=predict,
                    inputs=[gr.components.Image(type='pil'),
                            gr.components.Slider(minimum=512, maximum=1024, value=1024, step=64),
                            gr.components.Checkbox(value=True)],
                    outputs=['plot'],
                    # examples=[["assets/sa_8776.jpg", 1024, True]],
                    #    ["assets/sa_1309.jpg", 1024]],
                    examples=[["assets/sa_192.jpg"], ["assets/sa_414.jpg"],
                              ["assets/sa_561.jpg"], ["assets/sa_862.jpg"],
                              ["assets/sa_1309.jpg"], ["assets/sa_8776.jpg"],
                              ["assets/sa_10039.jpg"], ["assets/sa_11025.jpg"],],
                    cache_examples=False,
                    )

demo.launch()