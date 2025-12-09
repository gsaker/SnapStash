'use client';

import { Card } from "./ui/card"
import { Button } from "./ui/button"
import { Slider } from "./ui/slider"
import { Play, Pause, Download, Volume2, VolumeX, Maximize, SkipBack, SkipForward } from "lucide-react"
import { useState, useRef, useEffect } from "react"

interface EnhancedVideoPlayerProps {
  src: string
  isOwn: boolean
  fileName?: string
  fileSize?: number
  mimeType?: string
}

export function EnhancedVideoPlayer({ src, isOwn, fileName, fileSize, mimeType }: EnhancedVideoPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [totalDuration, setTotalDuration] = useState(0)
  const [volume, setVolume] = useState(1)
  const [isMuted, setIsMuted] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)
  const [showControls, setShowControls] = useState(true)
  const [showVolumeSlider, setShowVolumeSlider] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const controlsTimeoutRef = useRef<NodeJS.Timeout>()

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause()
      } else {
        videoRef.current.play()
      }
      setIsPlaying(!isPlaying)
    }
  }

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setTotalDuration(videoRef.current.duration)
      setIsLoaded(true)
    }
  }

  const handleSeek = (value: number[]) => {
    const newTime = value[0]
    if (videoRef.current) {
      videoRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const handleVolumeChange = (value: number[]) => {
    const newVolume = value[0]
    setVolume(newVolume)
    if (videoRef.current) {
      videoRef.current.volume = newVolume
    }
    setIsMuted(newVolume === 0)
  }

  const toggleMute = () => {
    if (videoRef.current) {
      const newMuted = !isMuted
      setIsMuted(newMuted)
      videoRef.current.muted = newMuted
      if (newMuted) {
        videoRef.current.volume = 0
      } else {
        videoRef.current.volume = volume
      }
    }
  }

  const skipForward = () => {
    if (videoRef.current) {
      const newTime = Math.min(videoRef.current.currentTime + 10, totalDuration)
      videoRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const skipBackward = () => {
    if (videoRef.current) {
      const newTime = Math.max(videoRef.current.currentTime - 10, 0)
      videoRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const toggleFullscreen = () => {
    if (videoRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen()
      } else {
        videoRef.current.requestFullscreen()
      }
    }
  }

  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${seconds.toString().padStart(2, "0")}`
  }

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const showControlsTemporarily = () => {
    setShowControls(true)
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current)
    }
    controlsTimeoutRef.current = setTimeout(() => {
      if (isPlaying) {
        setShowControls(false)
      }
    }, 3067)
  }

  const handleMouseMove = () => {
    showControlsTemporarily()
  }

  const handleVideoClick = () => {
    togglePlay()
    showControlsTemporarily()
  }

  useEffect(() => {
    return () => {
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!isPlaying) {
      setShowControls(true)
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current)
      }
    }
  }, [isPlaying])

  return (
    <Card className="overflow-hidden border-0 shadow-lg max-w-sm relative bg-black">
      <div
        className="relative group cursor-pointer"
        onMouseMove={handleMouseMove}
        onClick={handleVideoClick}
      >
        <video
          key={src}
          ref={videoRef}
          src={src}
          className="w-full h-auto rounded-lg object-cover"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={() => setIsPlaying(false)}
          preload="metadata"
          muted={isMuted}
        />
        
        {/* Play/Pause Overlay - only show when paused */}
        {!isPlaying && (
          <div className={`absolute inset-0 flex items-center justify-center transition-opacity duration-200 ${
            showControls ? 'opacity-100' : 'opacity-0'
          }`}>
            <Button
              size="lg"
              className="rounded-full bg-black/50 hover:bg-black/70 text-white border-0 pointer-events-none"
            >
              <Play className="w-8 h-8 ml-1" />
            </Button>
          </div>
        )}

        {/* Controls Overlay */}
        <div className={`absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent p-4 transition-opacity duration-200 ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}>

          {/* Progress Bar with Time */}
          <div className="mb-3 flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex-1">
              <Slider
                value={[currentTime]}
                max={totalDuration || 100}
                step={0.1}
                onValueChange={handleSeek}
                className="w-full"
                disabled={!isLoaded}
              />
            </div>
            <span className="text-xs text-white whitespace-nowrap">
              {isLoaded ? formatTime(currentTime) : "0:00"} / {isLoaded ? formatTime(totalDuration) : "0:00"}
            </span>
          </div>

          {/* Controls */}
          <div className="flex items-center justify-between text-white">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                className="rounded-full p-1 hover:bg-white/20 text-white"
                onClick={(e) => { e.stopPropagation(); skipBackward(); }}
                disabled={!isLoaded}
              >
                <SkipBack className="w-4 h-4" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="rounded-full p-1 hover:bg-white/20 text-white"
                onClick={(e) => { e.stopPropagation(); togglePlay(); }}
                disabled={!isLoaded}
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="rounded-full p-1 hover:bg-white/20 text-white"
                onClick={(e) => { e.stopPropagation(); skipForward(); }}
                disabled={!isLoaded}
              >
                <SkipForward className="w-4 h-4" />
              </Button>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={src}
                download
                className="rounded-full p-1 hover:bg-white/20 text-white"
                title="Download"
                onClick={(e) => e.stopPropagation()}
              >
                <Download className="w-4 h-4" />
              </a>
              
              <div className="relative flex items-center">
                <div
                  className="rounded-full p-1 hover:bg-white/20 text-white cursor-pointer flex items-center justify-center"
                  onMouseEnter={() => setShowVolumeSlider(true)}
                  onMouseLeave={() => setShowVolumeSlider(false)}
                  onClick={(e) => e.stopPropagation()}
                >
                  {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                </div>
                
                {/* Vertical Volume Slider */}
                <div 
                  className={`absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 transition-opacity duration-200 ${
                    showVolumeSlider ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
                  }`}
                  onMouseEnter={() => setShowVolumeSlider(true)}
                  onMouseLeave={() => setShowVolumeSlider(false)}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="bg-black/90 backdrop-blur-sm rounded-lg p-3 shadow-lg border border-white/10">
                    <div className="flex flex-col items-center">
                      <div 
                        className="w-1 h-16 bg-white/20 rounded-full relative cursor-pointer"
                        onClick={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          const y = e.clientY - rect.top;
                          const percentage = 1 - (y / rect.height); // Inverted for bottom-to-top
                          const newVolume = Math.max(0, Math.min(1, percentage));
                          handleVolumeChange([newVolume]);
                        }}
                      >
                        {/* Volume fill */}
                        <div 
                          className="absolute bottom-0 left-0 right-0 bg-white rounded-full transition-all duration-150"
                          style={{ height: `${(isMuted ? 0 : volume) * 100}%` }}
                        />
                        {/* Volume handle */}
                        <div 
                          className="absolute w-3 h-3 bg-white rounded-full shadow-lg transform -translate-x-1/2 -translate-y-1/2 cursor-grab active:cursor-grabbing border-2 border-black/20"
                          style={{ 
                            left: '50%',
                            top: `${100 - (isMuted ? 0 : volume) * 100}%`
                          }}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            const startY = e.clientY;
                            const startVolume = isMuted ? 0 : volume;
                            const trackHeight = 64; // h-16 = 4rem = 64px
                            
                            const handleMouseMove = (moveEvent: MouseEvent) => {
                              const deltaY = startY - moveEvent.clientY; // Inverted
                              const volumeChange = deltaY / trackHeight;
                              const newVolume = Math.max(0, Math.min(1, startVolume + volumeChange));
                              handleVolumeChange([newVolume]);
                            };
                            
                            const handleMouseUp = () => {
                              document.removeEventListener('mousemove', handleMouseMove);
                              document.removeEventListener('mouseup', handleMouseUp);
                            };
                            
                            document.addEventListener('mousemove', handleMouseMove);
                            document.addEventListener('mouseup', handleMouseUp);
                          }}
                        />
                      </div>
                      <div className="text-xs text-white/80 text-center mt-2 font-medium">
                        {Math.round((isMuted ? 0 : volume) * 100)}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <Button
                size="sm"
                variant="ghost"
                className="rounded-full p-1 hover:bg-white/20 text-white"
                onClick={(e) => { e.stopPropagation(); toggleFullscreen(); }}
              >
                <Maximize className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
